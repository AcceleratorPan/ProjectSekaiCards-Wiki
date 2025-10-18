urls = [
    "https://sekai.best/assets/chr_ts_1-CbhdBpye.png",
    "https://sekai.best/assets/chr_ts_2-B31RK2Xk.png",
    "https://sekai.best/assets/chr_ts_3-ZrVZfKrC.png",
    "https://sekai.best/assets/chr_ts_4-DvzRR1Re.png",
    "https://sekai.best/assets/chr_ts_5-D3BmQn7G.png",
    "https://sekai.best/assets/chr_ts_6-CFQFqzWC.png",
    "https://sekai.best/assets/chr_ts_7-BkQ55CaA.png",
    "https://sekai.best/assets/chr_ts_8-CePUM4gk.png",
    "https://sekai.best/assets/chr_ts_9-BbKZLCNl.png",
    "https://sekai.best/assets/chr_ts_10-BKDk2sEU.png",
    "https://sekai.best/assets/chr_ts_11-CLf2UAX9.png",
    "https://sekai.best/assets/chr_ts_12-CxI0-R8N.png",
    "https://sekai.best/assets/chr_ts_13-DCU02QHc.png",
    "https://sekai.best/assets/chr_ts_14-DwBPCXzM.png",
    "https://sekai.best/assets/chr_ts_15-DmN4JaEb.png",
    "https://sekai.best/assets/chr_ts_16-BgcUCF20.png",
    "https://sekai.best/assets/chr_ts_17-Ewrrn8Nn.png",
    "https://sekai.best/assets/chr_ts_18-DMQehbOD.png",
    "https://sekai.best/assets/chr_ts_19-CHX_VlCK.png",
    "https://sekai.best/assets/chr_ts_20-BwzsmJDI.png",
    "https://sekai.best/assets/chr_ts_21-DiBW6904.png",
    "https://sekai.best/assets/chr_ts_22-Bj3RnBX8.png",
    "https://sekai.best/assets/chr_ts_23-DP-KWJG0.png",
    "https://sekai.best/assets/chr_ts_24-riyYUsS2.png",
    "https://sekai.best/assets/chr_ts_25-BnERLtlr.png",
    "https://sekai.best/assets/chr_ts_26-l9r_QJnP.png"
]

dict = {1: '星乃 一歌 (ほしの いちか)', 2: '天馬 咲希 (てんま さき)', 3: '望月 穂波 (もちづき ほなみ)', 4: '日野森 志歩 (ひのもり しほ)', 5: '花里 みのり (はなさと みのり)', 6: '桐谷 遥 (きりたに はるか)', 7: '桃井 愛莉 (ももい あいり)', 8: '日野森 雫 (ひのもり しずく)', 9: '小豆沢 こはね (あずさわ こはね)', 10: '白石 杏 (しらいし あん)', 11: '東雲 彰人 (しののめ あきと)', 12: '青柳 冬弥 (あおやぎ とうや)', 13: '天馬 司 (てんま つかさ)', 14: '鳳 えむ (おおとり えむ)', 15: '草薙 寧々 (くさなぎ ねね)', 16: '神代 類 (かみしろ るい)', 17: '宵崎 奏 (よいさき かなで)', 18: '朝比奈 まふゆ (あさひな まふゆ)', 19: '東雲 絵名 (しののめ えな)', 20: '暁山 瑞希 (あきやま みずき)', 21: '初音 ミク (はつね みく)', 22: '鏡音 リン (かがみね りん)', 23: '鏡音 レン (かがみね れん)', 24: '巡音 ルカ (めぐりね るか)', 25: 'None MEIKO (None めいこ)', 26: 'None KAITO (None かいと)'}

import requests

session = requests.Session()

for i, url in enumerate(urls, start=1):
    filename = dict[i].replace(" ", "_").replace("(", "").replace(")", "").replace("'", "").replace("None_", "") + ".png"
    response = session.get(url)
    if response.status_code == 200:
        with open(filename, "wb") as f:
            f.write(response.content)
        print(f"Downloaded {filename}")
    else:
        print(f"Failed to download {filename}: Status code {response.status_code}")

