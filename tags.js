// 双层标签数据结构
export let tags = {
    "菜系": [
        "鲁菜",
        "粤菜",
        "川菜",
        "苏菜",
        "浙菜",
        "闽菜",
        "湘菜",
        "徽菜"
    ],
    "做法": [
        "卤制",
        "炒菜",
        "清蒸",
        "红烧",
        "凉拌",
        "炖菜",
        "蒸菜",
        "油炸",
        "烤制",
        "水煮"
    ],
    "品类": [
        "健康",
        "低脂",
        "软糯",
        "主食",
        "营养",
        "丰富"
    ],
    "口味": [
        "麻辣",
        "酸辣",
        "甜辣",
        "甜",
        "微辣",
        "重口",
        "清淡",
        "咸鲜"
    ],
    "其他": []
};

// 标签颜色配置
export const tagColors = {
    "鲁菜": { "backgroundColor": "#E74C3C", "color": "white" },
    "粤菜": { "backgroundColor": "#3498DB", "color": "white" },
    "川菜": { "backgroundColor": "#E67E22", "color": "white" },
    "苏菜": { "backgroundColor": "#9B59B6", "color": "white" },
    "浙菜": { "backgroundColor": "#1ABC9C", "color": "white" },
    "闽菜": { "backgroundColor": "#2ECC71", "color": "white" },
    "湘菜": { "backgroundColor": "#F39C12", "color": "white" },
    "徽菜": { "backgroundColor": "#D35400", "color": "white" },
    
    "卤制": { "backgroundColor": "#45B7D1", "color": "white" },
    "炒菜": { "backgroundColor": "#FF6B6B", "color": "white" },
    "清蒸": { "backgroundColor": "#FFEAA7", "color": "#333" },
    "红烧": { "backgroundColor": "#96CEB4", "color": "white" },
    "凉拌": { "backgroundColor": "#BB8FCE", "color": "white" },
    "炖菜": { "backgroundColor": "#4ECDC4", "color": "white" },
    "蒸菜": { "backgroundColor": "#AED6F1", "color": "#333" },
    "油炸": { "backgroundColor": "#F39C12", "color": "white" },
    "烤制": { "backgroundColor": "#E74C3C", "color": "white" },
    "水煮": { "backgroundColor": "#3498DB", "color": "white" },
    
    "健康": { "backgroundColor": "#58D68D", "color": "white" },
    "低脂": { "backgroundColor": "#85C1E9", "color": "white" },
    "软糯": { "backgroundColor": "#4d89b1ff", "color": "white" },
    "主食": { "backgroundColor": "#F39C12", "color": "white" },
    "营养": { "backgroundColor": "#DDA0DD", "color": "white" },
    "丰富": { "backgroundColor": "#98D8C8", "color": "#333" },
    
    "麻辣": { "backgroundColor": "#E74C3C", "color": "white" },
    "酸辣": { "backgroundColor": "#E67E22", "color": "white" },
    "甜辣": { "backgroundColor": "#9B59B6", "color": "white" },
    "甜": { "backgroundColor": "#FF69B4", "color": "white" },
    "微辣": { "backgroundColor": "#F39C12", "color": "white" },
    "重口": { "backgroundColor": "#F7DC6F", "color": "#333" },
    "清淡": { "backgroundColor": "#85C1E9", "color": "white" },
    "咸鲜": { "backgroundColor": "#27AE60", "color": "white" }
};

// 获取所有标签的扁平列表
export function getAllTags() {
    let allTags = [];
    Object.values(tags).forEach(subTags => {
        allTags = allTags.concat(subTags);
    });
    return allTags;
}

// 获取标签所属分类
export function getTagCategory(tag) {
    for (const [category, subTags] of Object.entries(tags)) {
        if (subTags.includes(tag)) {
            return category;
        }
    }
    return "其他";
}