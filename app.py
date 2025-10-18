import requests, sqlite3
import re, os, sys, time
from datetime import datetime
from tqdm import tqdm
from flask import Flask, render_template, redirect, g, abort, url_for, jsonify, request, session
from waitress import serve
import logging
import cv2
import numpy as np
from werkzeug.utils import secure_filename

# ===============================================================
# Flask 应用和配置
# ===============================================================
log = logging.getLogger('werkzeug')
# 将其日志级别设置为 ERROR，屏蔽 INFO 级别和 WARNING 级别的日志，包括请求日志
log.setLevel(logging.ERROR)
app = Flask(__name__)
# --- 要使用session，必须设置一个密钥 ---
# 在生产环境中，这应该是一个更复杂且保密的字符串
app.secret_key = os.urandom(24)
# --- 特征数据存储文件夹 和 上传文件夹 ---
UPLOAD_FOLDER = 'uploads'
FEATURES_FOLDER = 'features'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# 确保上传和特征文件夹存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(FEATURES_FOLDER, exist_ok=True)

# --- 配置 ---
CARDS_JSON_URL = "https://sekai-world.github.io/sekai-master-db-diff/cards.json"
ASSETS_BASE_URL = "https://storage.sekai.best/sekai-jp-assets/character/member/"
cwd = "/Users/acceleratorpan/Downloads/Proj/pjskCardsWeb"
RETRY = 3  # 下载失败时的重试次数
COMPARE_RESULT_COUNT = 5  # 比对结果返回的卡牌数量
os.chdir(cwd)
IMAGE_FOLDER = os.path.join("static", "webp")
JSON_FOLDER = os.path.join("static", "json")
DB_FILE = "cards.db"
characterNameDict = {}
characterUnitDict = {}
TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS Cards (
    id INTEGER PRIMARY KEY,
    assetbundleName TEXT,
    cardRarityType TEXT,
    characterName TEXT,
    characterUnit TEXT,
    attribute TEXT,
    description TEXT,
    cardSkillName TEXT,
    gachaPhrase TEXT,
    releaseTime TEXT,
    subscribed INTEGER DEFAULT 0
);
""" 

# ===============================================================
# 核心图像比对逻辑
# ===============================================================
# --- 用于计算和保存图像特征的辅助函数 ---
def calculate_and_save_features(image_path, feature_path):
    """读取图片，计算SIFT特征，并将其保存到文件。"""
    if not os.path.exists(image_path):
        return
    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return
        
        sift = cv2.SIFT_create()
        keypoints, descriptors = sift.detectAndCompute(img, None)

        # BFmatcher 需要至少两个描述符才能进行匹配
        # if keypoints is None or descriptors is None:
        #     return

        # # 将关键点对象转换为可序列化的Numpy数组
        # keypoints_np = np.array([[kp.pt[0], kp.pt[1], kp.size, kp.angle, kp.response, kp.octave, kp.class_id] for kp in keypoints])
        
        # # 使用Numpy的savez进行高效存储
        # np.savez(feature_path, keypoints=keypoints_np, descriptors=descriptors)
        
        # FlannBasedMatcher
        if descriptors is not None:
            # 使用Numpy的savez进行高效存储
            np.savez(feature_path, descriptors=descriptors)
        
    except Exception as e:
        print(f"\n处理特征失败: {image_path}, 错误: {e}")
        
def compare_images(uploaded_image_path):
    """
    使用OpenCV SIFT算法将上传的图片与本地图库进行比对。
    会根据卡牌稀有度，同时比对 normal 和 trained 两种图片。
    :param uploaded_image_path: 上传图片的路径。
    :return: 一个按匹配度排序的列表，每个元素是 (card_id, score)。
    !!upd: 通过加载预计算的特征来快速比对图片。
    """
    # --- 在函数内部建立独立的数据库连接，以查询卡牌信息 ---
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, cardRarityType FROM cards")
        all_cards = cursor.fetchall()
    except Exception as e:
        print(f"数据库查询失败: {e}")
        return []
    finally:
        if conn:
            conn.close()

    try:
        # 初始化SIFT检测器
        sift = cv2.SIFT_create()
        # 读取上传的图片并计算其特征
        img1 = cv2.imread(uploaded_image_path, cv2.IMREAD_GRAYSCALE)
        if img1 is None:
            print(f"错误: 无法读取上传的图片 {uploaded_image_path}")
            return []
        kp1, des1 = sift.detectAndCompute(img1, None)
        if des1 is None or len(kp1) == 0:
            print("错误: 无法从上传的图片中检测到特征点。")
            return []

        # BFMatcher
        # bf = cv2.BFMatcher()
        
        des1 = np.float32(des1) # 转换为FLANN所需的格式

        # --- 使用 FlannBasedMatcher ---
        FLANN_INDEX_KDTREE = 1
        index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
        search_params = dict(checks=50)
        flann = cv2.FlannBasedMatcher(index_params, search_params)
        
        # --- 使用字典来存储每个card_id的最高得分 ---
        best_scores = {}
        print("开始快速图像比对...")
        # --- 不再读取和处理图片，而是直接加载特征文件 ---
        for card_id, rarity in tqdm(all_cards, desc="比对进度"):
            images_to_check_stems = [f"{card_id}_normal"]
            if rarity in ['rarity_3', 'rarity_4']:
                images_to_check_stems.append(f"{card_id}_trained")

            for stem in images_to_check_stems:
                feature_path = os.path.join(FEATURES_FOLDER, f"{stem}.npz")
                
                if not os.path.exists(feature_path):
                    continue

                # 加载预计算的特征
                
                # BFMatcher
                # with np.load(feature_path) as data:
                #     keypoints_np = data['keypoints']
                #     des2 = data['descriptors']
                
                # if des2 is None or len(keypoints_np) < 2:
                #     continue

                # matches = bf.knnMatch(des1, des2, k=2)
                
                # FlannBasedMatcher
                with np.load(feature_path) as data:
                    des2 = data['descriptors']
                
                if des2 is None:
                    continue
                
                des2 = np.float32(des2) # 转换为FLANN所需的格式
                if len(des2) < 2: continue

                matches = flann.knnMatch(des1, des2, k=2)
                
                good_matches = []
                valid_matches = [m for m in matches if len(m) == 2]
                for m, n in valid_matches:
                    if m.distance < 0.75 * n.distance:
                        good_matches.append(m)
                
                score = (len(good_matches) / len(kp1)) * 100
                score = min(score, 100.0)

                if score > 5:
                    current_best = best_scores.get(card_id, 0)
                    if score > current_best:
                        best_scores[card_id] = score

        results = list(best_scores.items())
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results

    except Exception as e:
        print(f"图像比对过程中发生严重错误: {e}")
        return []

# ===============================================================
# 数据更新逻辑
# ====================== =========================================
headers = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://sekai.best/",
    "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
}

img_headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ja-JP;q=0.6,ja;q=0.5",
    "Cache-Control": "max-age=0",
    "If-Modified-Since": "Fri, 08 Aug 2025 03:59:14 GMT",
    "If-None-Match": '"275553a56736baca6e67fda9e6603619"',
    "Priority": "u=0, i",
    "Sec-CH-UA": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
}

def download_image(url, file_path):
    """下载单个图片文件并保存，最多重试 RETRY 次"""
    if os.path.exists(file_path):
        return True  # 文件已存在，直接返回True
    
    for attempt in range(RETRY):  # 循环3次
        try:
            # 增加 timeout 参数防止请求卡死
            response = requests.get(url, stream=True, timeout=5)
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                return True  # 下载成功，直接返回True并退出函数
            # 如果状态码不是200，也算作一次失败的尝试
        except requests.exceptions.RequestException as e:
            pass
        # 如果代码运行到这里，说明本次尝试失败
        if attempt < 2:
            time.sleep(0.5)

    # 如果循环3次都失败了，则打印最终的失败信息
    print(f"\n下载失败，已达最大重试次数: {url}")
    return False

def readCharacterUnit():
    with open(os.path.join(JSON_FOLDER, "unit_profile.json"), "r", encoding="utf-8") as f:
        unit_data = f.read()
        unit_data = re.sub(r'\/\/.*', '', unit_data)  # Remove comments
        unit_data = re.sub(r',\s*}', '}', unit_data)  # Remove trailing commas
        unit_data = re.sub(r',\s*]', ']', unit_data)  # Remove trailing commas
        unitNameDict = eval(unit_data)
    return unitNameDict

def readCharacterName():
    characterNameDict = {}
    characterUnitDict = {}
    unitNameDict = readCharacterUnit()

    with open(os.path.join(JSON_FOLDER, "gameCharacters.json"), "r", encoding="utf-8") as f:
        character_data = f.read()
        character_data = re.sub(r'\/\/.*', '', character_data)  # Remove comments
        character_data = re.sub(r',\s*}', '}', character_data)  # Remove trailing commas
        character_data = re.sub(r',\s*]', ']', character_data)  # Remove trailing commas
        character_list = eval(character_data)
        for character in character_list:
            characterId = character.get('id')
            if character.get('firstName'):
                characterName = f"{character.get('firstName')} {character.get('givenName')} ({character.get('firstNameRuby')} {character.get('givenNameRuby')})"
            else:
                characterName = f"{character.get('givenName')} ({character.get('givenNameRuby')})"
            characterUnit = unitNameDict[character.get('unit', {})].get('name', "Unknown")
            if characterId:
                characterNameDict[characterId] = characterName
                characterUnitDict[characterId] = characterUnit
    return characterNameDict, characterUnitDict

def getCharacterName(characterId):
    return characterNameDict.get(characterId, "Unknown")

def getCharacterUnit(characterId):
    return characterUnitDict.get(characterId, "Unknown")

def unixTimeStampToDateString(timestamp):
    if timestamp:
        dt = datetime.fromtimestamp(timestamp / 1000)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return "Unknown"

def setup_database():
    """连接数据库并创建表（如果不存在）"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(TABLE_SCHEMA)
    conn.commit()
    return conn, cursor

def get_existing_card_ids(cursor):
    """从数据库获取所有已保存的卡牌ID"""
    cursor.execute("SELECT id FROM cards")
    return {row[0] for row in cursor.fetchall()}

def get_all_cards(cursor):
    cursor.execute("SELECT * FROM Cards")
    return cursor.fetchall()

def update_local_data():
    """执行数据更新的核心函数"""
    print("--- 正在初始化环境 ---")
    conn, cursor = setup_database()
    os.makedirs(IMAGE_FOLDER, exist_ok=True)
    print(f"数据库 '{DB_FILE}' 和图片文件夹 '{IMAGE_FOLDER}' 已准备就绪。")

    print(f"\n--- 正在从URL获取最新卡牌列表 ---")
    try:
        response = requests.get(CARDS_JSON_URL)
        response.raise_for_status()
        all_cards_data = response.json()
    except Exception as e:
        print(f"错误：无法获取或解析 cards.json。{e}")
        conn.close()
        return

    existing_ids = get_existing_card_ids(cursor)
    new_cards = [card for card in all_cards_data if card.get("id") not in existing_ids]

    # with open(os.path.join(JSON_FOLDER, "new_cards.json"), "w", encoding="utf-8") as f:
    #     json.dump(new_cards, f, ensure_ascii=False, indent=4)
    # print(f"已保存 new_cards.json 文件，共 {len(new_cards)} 张卡牌。")
    
    if not new_cards:
        print("\n--- 所有卡牌均已是最新，无需更新。 ---")
        conn.close()
        return
    
    print(f"\n--- 发现 {len(new_cards)} 张新卡牌，开始处理... ---")
    try:
        with tqdm(total=len(new_cards), desc="下载并预处理新卡牌") as pbar:
            for card in new_cards:
                card_id = card.get("id")
                asset_name = card.get("assetbundleName")
                if not card_id or not asset_name:
                    pbar.update(1)
                    continue
                
                download_success = True
                # 下载卡面图片 (分为训练前后)
                img_url_normal = f"{ASSETS_BASE_URL}{asset_name}/card_normal.webp"
                img_path_normal = os.path.join(IMAGE_FOLDER, f"{card_id}_normal.webp")
                if download_image(img_url_normal, img_path_normal):
                    feature_path_normal = os.path.join(FEATURES_FOLDER, f"{card_id}_normal.npz")
                    calculate_and_save_features(img_path_normal, feature_path_normal)
                else:
                    download_success = False

                if card.get("cardRarityType") in ["rarity_3", "rarity_4"]:
                    img_url_trained = f"{ASSETS_BASE_URL}{asset_name}/card_after_training.webp"
                    img_path_trained = os.path.join(IMAGE_FOLDER, f"{card_id}_trained.webp")
                    if download_image(img_url_trained, img_path_trained):
                        feature_path_trained = os.path.join(FEATURES_FOLDER, f"{card_id}_trained.npz")
                        calculate_and_save_features(img_path_trained, feature_path_trained)
                    else:
                        download_success = False

                if not download_success:
                    print(f"跳过卡牌 ID {card_id}，因图片下载失败。")
                    pbar.update(1)
                    continue
                
                cursor.execute("""
                        INSERT INTO Cards (id, assetbundleName, cardRarityType, characterName, characterUnit,  attribute, description, cardSkillName, gachaPhrase, releaseTime)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        card.get("id"),
                        card.get('assetbundleName'),
                        card.get('cardRarityType'),
                        getCharacterName(card.get('characterId')),
                        getCharacterUnit(card.get('characterId')),
                        card.get('attr'),
                        card.get('prefix'),
                        card.get('cardSkillName'),
                        card.get('gachaPhrase'),
                        unixTimeStampToDateString(card.get('releaseAt'))
                    ))
                conn.commit()
                pbar.update(1)
    finally:
        conn.close()
        print("\n--- 更新流程结束 ---")

# ===============================================================
# Flask Web 应用逻辑
# ===============================================================
def get_db():
    """获取当前请求的数据库连接"""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row  # 让查询结果可以像字典一样访问列
    return g.db

@app.route('/')
def root():
    return redirect('/cards')

@app.teardown_appcontext
def close_db(exception):
    """在应用上下文结束时关闭数据库连接"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

@app.route('/cards')
def show_cards():
    """卡牌网格主页"""
    session['last_cards_url'] = request.full_path
    db = get_db()
    cursor = db.cursor()
    
    # --- 筛选逻辑 ---
    query_base = "SELECT id, cardRarityType, description, characterName, attribute, subscribed FROM cards"
    conditions = []
    params = []

    # 从URL获取筛选参数
    selected_characters = request.args.getlist('character')
    selected_attrs = request.args.getlist('attr')
    selected_rarities = request.args.getlist('rarity')
    search_desc = request.args.get('desc', '')
    selected_subscribed = request.args.get('subscribed', '')

    if selected_characters:
        conditions.append(f"characterName IN ({','.join(['?']*len(selected_characters))})")
        params.extend(selected_characters)
    
    if selected_attrs:
        conditions.append(f"attribute IN ({','.join(['?']*len(selected_attrs))})")
        params.extend(selected_attrs)

    if selected_rarities:
        conditions.append(f"cardRarityType IN ({','.join(['?']*len(selected_rarities))})")
        params.extend(selected_rarities)
    
    if search_desc:
        conditions.append("description LIKE ?")
        params.append(f"%{search_desc}%")
        
    if selected_subscribed == '1':
        conditions.append("subscribed = 1")
    
    order_clause = "ORDER BY releaseTime DESC, id ASC"

    # 动态构建SQL查询
    if conditions:
        query = f"{query_base} WHERE {' AND '.join(conditions)} {order_clause}"
    else:
        query = f"{query_base} {order_clause}"

    cursor.execute(query, params)
    all_rows = cursor.fetchall()
    
    cards_list = []
    preload_images = set()
    preload_images.add(url_for('static', filename='png/rarity_star_trained.png'))


    for card_row in all_rows:    
        card_dict = dict(card_row)
        if card_dict['cardRarityType'] in ['rarity_3', 'rarity_4']:
            preload_images.add(url_for('static', filename=f"webp/{card_dict['id']}_trained.webp"))
        
        cards_list.append(card_dict)

    # 准备筛选菜单所需的数据
    filter_options = {
        'characters': characterNameDict.values(),
        'attributes': ['cute', 'cool', 'pure', 'happy', 'mysterious'],
        'rarities': {
            'rarity_4': 4,
            'rarity_3': 3,
            'rarity_2': 2,
            'rarity_1': 1,
            'rarity_birthday': 1 # 生日卡也只显示1颗特殊的星
        }
    }

    # 将当前选择的筛选器也传递给模板
    selected_filters = {
        'characters': selected_characters,
        'attributes': selected_attrs,
        'rarities': selected_rarities,
        'desc': search_desc,
        'subscribed': selected_subscribed
    }
        
    return render_template(
        'cards.html', 
        cards=cards_list, 
        preload_images=list(preload_images),
        filter_options=filter_options,
        selected_filters=selected_filters
    )

@app.route('/cards/<int:card_id>')
def card_detail(card_id):
    """卡牌详情页"""
    back_url = session.get('last_cards_url', url_for('show_cards'))
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
    card = dict(cursor.fetchone())
    # 如果找不到卡牌，返回404错误
    if card is None:
        abort(404)
    return render_template('card_detail.html', card=card, back_url=back_url)

@app.route('/card/toggle_subscription', methods=['POST'])
def toggle_subscription():
    """处理收藏状态切换的API端点"""
    db = get_db()
    cursor = db.cursor()
    data = request.get_json()
    card_id = data.get('card_id')
    if not card_id:
        return jsonify({'success': False, 'error': 'Missing card_id'}), 400
    try:
        cursor.execute("UPDATE cards SET subscribed = 1 - subscribed WHERE id = ?", (card_id,))
        db.commit()
        cursor.execute("SELECT subscribed FROM cards WHERE id = ?", (card_id,))
        new_status = cursor.fetchone()['subscribed']
        return jsonify({'success': True, 'new_status': new_status})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/compare', methods=['POST'])
def compare():
    """接收上传的图片，执行比对，并将结果存入session"""
    if 'image' not in request.files:
        return redirect(url_for('show_cards'))
    
    file = request.files['image']

    if file.filename == '':
        return redirect(url_for('show_cards'))

    if file:
        filename = secure_filename(file.filename)
        uploaded_image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(uploaded_image_path)
        
        results = compare_images(uploaded_image_path)
        
        session['compare_results'] = results[:min(COMPARE_RESULT_COUNT, len(results))]

        os.remove(uploaded_image_path)
        
        return redirect(url_for('compare_results'))

@app.route('/compare_results')
def compare_results():
    """从session中读取比对结果并显示"""
    results_data = session.get('compare_results', [])
    if not results_data:
        return render_template('compare_results.html', results=[])

    # --- 为本页的“返回列表”按钮准备URL ---
    back_to_cards_url = session.get('last_cards_url', url_for('show_cards'))
    
    db = get_db()
    cursor = db.cursor()
    
    top_results = []
    preload_images = set()
    preload_images.add(url_for('static', filename='png/rarity_star_trained.png'))
    
    for card_id, score in results_data:
        cursor.execute("SELECT id, cardRarityType, characterName, description, attribute FROM cards WHERE id = ?", (card_id,))
        card_row = cursor.fetchone()
        if card_row:
            card_dict = dict(card_row)
            card_dict['score'] = f"{score:.2f}%"
            top_results.append(card_dict)
            if card_dict['cardRarityType'] in ['rarity_3', 'rarity_4']:
                preload_images.add(url_for('static', filename=f"webp/{card_dict['id']}_trained.webp"))

    return render_template('compare_results.html', results=top_results, preload_images=list(preload_images), back_to_cards_url=back_to_cards_url)

if __name__ == '__main__':  
    characterNameDict, characterUnitDict = readCharacterName()

    # 检查命令行参数，如果为 "update"，则执行更新逻辑
    if len(sys.argv) > 1 and sys.argv[1] == 'update':
        update_local_data()
    else:
        # 否则，启动Web服务器
        # print("启动Flask服务器。访问 http://127.0.0.1:5000/cards")
        # print("要更新数据，请停止服务器并运行: python app.py update")
        # app.run(debug=True)
        # --- 使用 Waitress 启动生产模式服务器 ---
        print("在生产模式下启动服务器...")
        print("服务运行于 http://127.0.0.1:7869")
        print("访问 http://127.0.0.1:7869/cards")
        serve(app, host='0.0.0.0', port=7869)