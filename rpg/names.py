import random

SURNAMES = (
    ("Li", "李"), ("Wang", "王"), ("Zhang", "张"), ("Liu", "刘"), ("Chen", "陈"), ("Yang", "杨"), ("Zhao", "赵"), ("Huang", "黄"),
    ("Zhou", "周"), ("Wu", "吴"), ("Xu", "徐"), ("Sun", "孙"), ("Ma", "马"), ("Zhu", "朱"), ("Hu", "胡"), ("Lin", "林"),
    ("Gu", "顾"), ("Shen", "沈"), ("Han", "韩"), ("Tang", "唐"), ("Feng", "冯"), ("Xiao", "萧"), ("Lu", "陆"), ("Jiang", "江"),
    ("Bai", "白"), ("Mo", "莫"), ("Su", "苏"), ("Ye", "叶"), ("Yan", "严"), ("Murong", "慕容"), ("Ouyang", "欧阳"),
    ("Situ", "司徒"), ("Linghu", "令狐"), ("Dongfang", "东方"), ("Xuanyuan", "轩辕"), ("Gongsun", "公孙"), ("Shangguan", "上官"),
)

GIVEN = (
    ("Qing", "清"), ("Yun", "云"), ("Feng", "风"), ("Yue", "月"), ("Hao", "浩"), ("Lan", "兰"), ("Ruo", "若"), ("Xue", "雪"),
    ("Chen", "辰"), ("Ming", "明"), ("Zhi", "芝"), ("Wen", "文"), ("Yu", "玉"), ("Xuan", "玄"), ("Jing", "静"), ("Tian", "天"),
    ("Han", "寒"), ("Mei", "梅"), ("Shan", "山"), ("Long", "龙"), ("Hua", "华"), ("Xin", "心"), ("Lei", "雷"), ("Ling", "灵"),
    ("Ze", "泽"), ("Ning", "宁"), ("Heng", "恒"), ("Yan", "燕"), ("Bo", "博"), ("Rui", "瑞"), ("Zi", "紫"), ("Wei", "卫"),
    ("Jian", "剑"), ("Qiu", "秋"), ("Shuang", "霜"), ("Tao", "涛"), ("Lian", "莲"), ("Kun", "昆"), ("Hong", "鸿"), ("Mu", "木"),
)

CLANS = (
    ("Azure Crane", "青鹤"), ("Nine Mulberry", "九桑"), ("Thousand Peak", "千峰"), ("Cold Moon", "寒月"), ("Iron Banner", "铁旗"),
    ("Jade Lotus", "玉莲"), ("Vermilion Bird", "朱雀"), ("Black Tortoise", "玄龟"), ("Silver Orchid", "银兰"), ("Scarlet Flame", "赤焰"),
    ("Hidden Dragon", "潜龙"), ("Autumn Sword", "秋剑"), ("Ten Thousand Pines", "万松"), ("Starfall", "坠星"), ("Ashen Lantern", "灰灯"),
)


def person(rng=None) -> tuple[str, str]:
    rng = rng or random
    surname = rng.choice(SURNAMES)
    given = rng.sample(GIVEN, rng.choice((1, 2)))
    name = surname[0] + " " + "".join(part[0] for part in given).capitalize()
    zh = surname[1] + "".join(part[1] for part in given)
    return name, zh


def clan(rng=None) -> tuple[str, str]:
    rng = rng or random
    name, zh = rng.choice(CLANS)
    return name, zh + "家"
