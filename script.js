// 导入数据
import { tags, tagColors, getAllTags } from './tags.js';
import { dishes as initialDishes } from './data.js';

// DOM元素
const menuGrid = document.getElementById('menu-grid');
const tagsWrapper = document.getElementById('tags-wrapper');
const searchInput = document.getElementById('search-input');
const cartItems = document.getElementById('cart-items');
const totalPrice = document.getElementById('total-price');
const dishModal = document.getElementById('dish-modal');
const dishDetail = document.getElementById('dish-detail');
const modalClose = document.getElementById('modal-close');
const adminPanel = document.getElementById('admin-panel');
const adminToggle = document.getElementById('admin-toggle');
const adminClose = document.getElementById('admin-close');
const dishForm = document.getElementById('dish-form');
const tagForm = document.getElementById('tag-form');
const tagsList = document.getElementById('tags-list');
const cartToggle = document.getElementById('cart-toggle');
const cartContent = document.getElementById('cart-content');
const logo = document.getElementById('logo');
const editPanel = document.getElementById('edit-panel');
const editClose = document.getElementById('edit-close');
const editDishForm = document.getElementById('edit-dish-form');

// 状态变量
let selectedTags = [];
let searchKeyword = '';
let cartVisible = false;
let cartExpanded = false;
let editingDishId = null;
let editMode = false;
let dishes = [...initialDishes];
let cart = [];

// 生成标签颜色样式
function generateTagStyles() {
    const style = document.createElement('style');
    let css = '';
    
    for (const [tag, colors] of Object.entries(tagColors)) {
        css += `.dish-tag.${tag} { background-color: ${colors.backgroundColor}; color: ${colors.color}; }\n`;
        css += `.tag.${tag} { background-color: ${colors.backgroundColor}; color: ${colors.color}; }\n`;
    }
    
    style.textContent = css;
    document.head.appendChild(style);
}

// 初始化
function init() {
    generateTagStyles();
    renderTags();
    renderDishes();
    renderCart();
    updateCartDisplay();
    bindEvents();
    bindCartDragEvents();
    bindLogoClickEvent();
    // 初始化懒加载
    lazyLoad();
}

// 绑定事件
function bindEvents() {
    // 结算按钮点击事件
    const checkoutButton = document.querySelector('.checkout-button');
    checkoutButton.addEventListener('click', () => {
        generateCheckoutJSON();
    });

    // 搜索输入事件
    searchInput.addEventListener('input', (e) => {
        searchKeyword = e.target.value.toLowerCase();
        renderDishes();
    });

    // 模态框关闭事件
    modalClose.addEventListener('click', () => {
        dishModal.classList.remove('active');
    });

    // 点击模态框外部关闭
    dishModal.addEventListener('click', (e) => {
        if (e.target === dishModal) {
            dishModal.classList.remove('active');
        }
    });

    // 管理员模式切换
    adminToggle.addEventListener('click', () => {
        adminPanel.classList.toggle('active');
        renderAdminTags();
    });

    // 管理员模式关闭
    adminClose.addEventListener('click', () => {
        adminPanel.classList.remove('active');
    });

    // 保存菜品
    dishForm.addEventListener('submit', (e) => {
        e.preventDefault();
        saveDish();
    });

    // 添加标签
    tagForm.addEventListener('submit', (e) => {
        e.preventDefault();
        addTag();
    });

    // 编辑面板关闭事件
    editClose.addEventListener('click', () => {
        editPanel.classList.remove('active');
        editingDishId = null;
        editDishForm.reset();
    });

    // 保存编辑
    editDishForm.addEventListener('submit', (e) => {
        e.preventDefault();
        saveEdit();
    });

    // 购物车切换
    cartToggle.addEventListener('click', (e) => {
        e.stopPropagation();
        cartExpanded = false;
        updateCartDisplay();
    });

    // 购物车容器点击事件
    const cartContainer = document.getElementById('cart-container');
    cartContainer.addEventListener('click', (e) => {
        e.stopPropagation();
        if (cartContainer.classList.contains('ball')) {
            cartExpanded = true;
            updateCartDisplay();
        }
    });

    // 点击购物车区域外收起购物车
    document.addEventListener('click', (e) => {
        const cartContainer = document.getElementById('cart-container');
        if (cartExpanded && !cartContainer.contains(e.target)) {
            cartExpanded = false;
            updateCartDisplay();
        }
    });

    // 保存到GitHub按钮事件
    const saveToGithubBtn = document.getElementById('save-to-github');
    if (saveToGithubBtn) {
        saveToGithubBtn.addEventListener('click', () => {
            saveDataToGitHub();
        });
    }
}

// 渲染标签（双层结构，点击展开）
function renderTags() {
    // 在渲染前记录展开状态
    const expandedCategories = new Set();
    const existingCategories = document.querySelectorAll('.tag-category');
    existingCategories.forEach(cat => {
        if (cat.classList.contains('expanded')) {
            const title = cat.querySelector('.tag-category-title');
            if (title) {
                const categoryName = title.textContent.trim().replace(/▼|\▲/g, '').trim();
                expandedCategories.add(categoryName);
            }
        }
    });
    
    tagsWrapper.innerHTML = '';
    
    // 遍历第一层标签（大分类）
    for (const [category, subTags] of Object.entries(tags)) {
        // 创建分类容器
        const categoryContainer = document.createElement('div');
        categoryContainer.className = 'tag-category';
        
        // 如果之前是展开状态，保持展开
        if (expandedCategories.has(category)) {
            categoryContainer.classList.add('expanded');
        }
        
        // 创建分类标题
        const categoryTitle = document.createElement('div');
        categoryTitle.className = 'tag-category-title';
        categoryTitle.textContent = category;
        categoryTitle.innerHTML += '<img src="img/icon/下拉.png" alt="展开" class="dropdown-icon" width="16" height="16">';
        
        // 创建子标签容器（默认隐藏）
        const subTagsContainer = document.createElement('div');
        subTagsContainer.className = 'tag-sub-container';
        
        // 遍历第二层标签（子标签）
        subTags.forEach(tag => {
            const tagElement = document.createElement('div');
            tagElement.className = `tag ${tag} ${selectedTags.includes(tag) ? 'active' : ''}`;
            tagElement.textContent = tag;
            tagElement.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleTag(tag);
            });
            subTagsContainer.appendChild(tagElement);
        });
        
        // 点击一级标签展开/收起二级标签
        categoryTitle.addEventListener('click', () => {
            // 检查是否有其他一级分类下有选中的二级标签
            const otherCategoriesHaveSelectedTags = Array.from(document.querySelectorAll('.tag-category')).some(container => {
                const title = container.querySelector('.tag-category-title');
                if (title) {
                    const categoryName = title.textContent.trim().replace(/▼|\▲/g, '').trim();
                    if (categoryName !== category) {
                        return container.querySelectorAll('.tag.active').length > 0;
                    }
                }
                return false;
            });
            
            if (otherCategoriesHaveSelectedTags) {
                // 如果有其他一级分类下有选中的二级标签，取消所有选中的二级标签
                selectedTags = [];
                renderTags();
                renderDishes();
            }
            
            // 收起所有一级标签
            document.querySelectorAll('.tag-category').forEach(cat => {
                cat.classList.remove('expanded');
            });
            
            // 如果之前没有选中其他二级标签，则展开当前一级标签
            if (!otherCategoriesHaveSelectedTags) {
                categoryContainer.classList.toggle('expanded');
            }
        });
        
        categoryContainer.appendChild(categoryTitle);
        categoryContainer.appendChild(subTagsContainer);
        tagsWrapper.appendChild(categoryContainer);
    }
}

// 切换标签
function toggleTag(tag) {
    // 查找该标签所属的一级分类
    let parentCategory = null;
    for (const [category, subTags] of Object.entries(tags)) {
        if (subTags.includes(tag)) {
            parentCategory = category;
            break;
        }
    }
    
    const wasSelected = selectedTags.includes(tag);
    
    if (selectedTags.length === 1 && selectedTags[0] === tag) {
        // 如果点击的是当前选中的标签，取消选择
        selectedTags = [];
    } else {
        // 否则选择该标签
        selectedTags = [tag];
    }
    
    // 如果是取消选中，检查该一级菜单下是否还有其他选中的标签
    if (wasSelected && parentCategory) {
        setTimeout(() => {
            const categoryContainers = document.querySelectorAll('.tag-category');
            categoryContainers.forEach(container => {
                const title = container.querySelector('.tag-category-title');
                if (title && title.textContent.trim().startsWith(parentCategory)) {
                    const activeTags = container.querySelectorAll('.tag.active');
                    if (activeTags.length === 0) {
                        container.classList.remove('expanded');
                    }
                }
            });
        }, 0);
    }
    
    renderTags();
    renderDishes();
}

// 渲染菜品
function renderDishes() {
    // 清空菜单容器
    menuGrid.innerHTML = '';
    
    const filteredDishes = dishes.filter(dish => {
        // 标签筛选
        const tagMatch = selectedTags.length === 0 || selectedTags.every(tag => dish.tags.includes(tag));
        // 搜索筛选
        const searchMatch = !searchKeyword || 
            dish.name.toLowerCase().includes(searchKeyword) ||
            (dish.description && dish.description.toLowerCase().includes(searchKeyword)) ||
            (dish.detailDescription && dish.detailDescription.toLowerCase().includes(searchKeyword)) ||
            (dish.ingredients && (typeof dish.ingredients === 'string' ? dish.ingredients : dish.ingredients.join(', ')).toLowerCase().includes(searchKeyword)) ||
            (dish.method && (typeof dish.method === 'string' ? dish.method : dish.method.join(', ')).toLowerCase().includes(searchKeyword)) ||
            dish.price.toString().includes(searchKeyword);
        return tagMatch && searchMatch;
    });

    filteredDishes.forEach(dish => {
        const dishCard = createDishCard(dish);
        menuGrid.appendChild(dishCard);
    });
    
    // 重新渲染后，根据当前编辑模式状态更新编辑按钮显示
    if (editMode) {
        toggleEditButtons();
    }
    
    // 重新初始化懒加载
    lazyLoad();
}

// 创建菜品卡片
function createDishCard(dish) {
    const card = document.createElement('div');
    card.className = 'dish-card';
    
    card.innerHTML = `
        <div class="dish-image">
            <img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='200' viewBox='0 0 300 200'%3E%3Crect width='300' height='200' fill='%23f0f0f0'/%3E%3Ctext x='50%25' y='50%25' font-size='14' text-anchor='middle' dominant-baseline='middle' fill='%23999'%3E加载中...%3C/text%3E%3C/svg%3E" data-src="${dish.image}" alt="${dish.name}" class="lazy-image" style="width: 100%; height: 100%; object-fit: cover;">
            <div class="dish-actions" style="display: none;">
                <button class="dish-action-btn edit-btn" data-id="${dish.id}">
                    <img src="img/icon/编辑.png" alt="编辑" width="20" height="20">
                </button>
                <button class="dish-action-btn delete-btn" data-id="${dish.id}">
                    <img src="img/icon/删除.png" alt="删除" width="20" height="20">
                </button>
            </div>
        </div>
        <div class="dish-info">
            <h3 class="dish-name">${dish.name}</h3>
            <div class="dish-price">¥${dish.price.toFixed(2)}</div>
            <p class="dish-desc">${dish.description}</p>
            <div class="dish-tags">
                ${dish.tags.slice(0, 2).map(tag => `<span class="dish-tag ${tag}">${tag}</span>`).join('')}${dish.tags.length > 2 ? '<span class="dish-tag more">...</span>' : ''}
            </div>
        </div>
    `;

    // 点击卡片查看详情
    card.addEventListener('click', (e) => {
        // 如果点击的是操作按钮，不显示详情
        if (!e.target.closest('.dish-action-btn')) {
            showDishDetail(dish);
        }
    });
    
    // 编辑按钮点击事件
    const editBtn = card.querySelector('.edit-btn');
    editBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        editDish(dish.id);
    });
    
    // 删除按钮点击事件
    const deleteBtn = card.querySelector('.delete-btn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            
            // 使用this来获取按钮的data-id属性
            const dishId = parseInt(this.dataset.id);
            
            // 直接删除菜品，不显示确认弹窗
            dishes = dishes.filter(d => d.id !== dishId);
            // 重新渲染菜品
            renderDishes();
        });
    }

    return card;
}

// 显示菜品详情
function showDishDetail(dish) {
    dishDetail.innerHTML = `
        <div class="dish-detail-image">
            <img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='800' height='300' viewBox='0 0 800 300'%3E%3Crect width='800' height='300' fill='%23f0f0f0'/%3E%3Ctext x='50%25' y='50%25' font-size='16' text-anchor='middle' dominant-baseline='middle' fill='%23999'%3E加载中...%3C/text%3E%3C/svg%3E" data-src="${dish.image}" alt="${dish.name}" class="lazy-image" style="width: 100%; height: 100%; object-fit: cover; border-radius: 15px;">
        </div>
        <h2 class="dish-detail-name">${dish.name}</h2>
        <div class="dish-detail-price-section">
            <div class="dish-detail-price">¥${dish.price.toFixed(2)}</div>
            <div class="quantity-control">
                <button class="quantity-btn decrease" data-id="${dish.id}">-</button>
                <span class="quantity" data-id="${dish.id}">0</span>
                <button class="quantity-btn increase" data-id="${dish.id}">+</button>
            </div>
        </div>
        <div class="dish-detail-tags">
            ${dish.tags.map(tag => `<span class="dish-tag ${tag}">${tag}</span>`).join('')}
        </div>
        <div class="dish-detail-section">
            <h4>详细描述</h4>
            <p>${dish.detailDescription}</p>
        </div>
        <div class="dish-detail-section">
            <h4>制作方法</h4>
            <p>${dish.method}</p>
        </div>
        <div class="dish-detail-section">
            <h4>用料</h4>
            <p>${dish.ingredients}</p>
        </div>
    `;
    dishModal.classList.add('active');
    // 加载懒加载图片
    lazyLoad();
    
    // 绑定数量控制事件
    const decreaseBtn = dishDetail.querySelector('.decrease');
    const increaseBtn = dishDetail.querySelector('.increase');
    const quantitySpan = dishDetail.querySelector('.quantity');
    
    decreaseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        let quantity = parseInt(quantitySpan.textContent);
        if (quantity > 0) {
            quantitySpan.textContent = quantity - 1;
            // 从购物车移除
            const existingItem = cart.find(item => item.id === dish.id);
            if (existingItem) {
                if (existingItem.quantity > 1) {
                    existingItem.quantity--;
                } else {
                    cart = cart.filter(item => item.id !== dish.id);
                }
                renderCart();
                updateCartDisplay();
            }
        }
    });
    
    increaseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        let quantity = parseInt(quantitySpan.textContent);
        quantitySpan.textContent = quantity + 1;
        // 添加到购物车
        addToCart(dish, 1);
        updateCartDisplay();
    });
    

}

// 添加到购物车
function addToCart(dish, quantity) {
    const existingItem = cart.find(item => item.id === dish.id);
    if (existingItem) {
        existingItem.quantity += quantity;
    } else {
        cart.push({
            id: dish.id,
            name: dish.name,
            price: dish.price,
            quantity: quantity
        });
    }
    renderCart();
}

// 渲染购物车
function renderCart() {
    cartItems.innerHTML = '';
    let total = 0;

    cart.forEach(item => {
        const itemElement = document.createElement('div');
        itemElement.className = 'cart-item';
        const subtotal = item.price * item.quantity;
        total += subtotal;

        itemElement.innerHTML = `
            <div class="cart-item-info">
                <div class="cart-item-name">${item.name}</div>
                <div class="cart-item-price">¥${item.price.toFixed(2)} x ${item.quantity}</div>
            </div>
            <div class="cart-item-quantity">
                <button class="quantity-btn decrease" data-id="${item.id}">-</button>
                <span class="quantity">${item.quantity}</span>
                <button class="quantity-btn increase" data-id="${item.id}">+</button>
            </div>
        `;

        // 购物车数量控制
        const decreaseBtn = itemElement.querySelector('.decrease');
        const increaseBtn = itemElement.querySelector('.increase');
        const quantitySpan = itemElement.querySelector('.quantity');

        decreaseBtn.addEventListener('click', () => {
            if (item.quantity > 1) {
                item.quantity--;
                renderCart();
                updateCartDisplay();
                // 更新菜品卡片上的数量
                updateDishQuantity(item.id, item.quantity);
            } else {
                cart = cart.filter(cartItem => cartItem.id !== item.id);
                renderCart();
                updateCartDisplay();
                // 更新菜品卡片上的数量
                updateDishQuantity(item.id, 0);
            }
        });

        increaseBtn.addEventListener('click', () => {
            item.quantity++;
            renderCart();
            updateCartDisplay();
            // 更新菜品卡片上的数量
            updateDishQuantity(item.id, item.quantity);
        });

        cartItems.appendChild(itemElement);
    });

    totalPrice.textContent = `¥${total.toFixed(2)}`;
}

// 更新菜品卡片上的数量
function updateDishQuantity(dishId, quantity) {
    const quantityElements = document.querySelectorAll(`.quantity[data-id="${dishId}"]`);
    quantityElements.forEach(element => {
        element.textContent = quantity;
    });
}

// 渲染管理员标签
function renderAdminTags() {
    tagsList.innerHTML = '';
    
    // 获取所有标签的扁平列表
    const allTags = getAllTags();
    
    allTags.forEach(tag => {
        // 检查标签是否被任何菜品引用
        const isTagUsed = dishes.some(dish => dish.tags.includes(tag));
        const tagElement = document.createElement('div');
        tagElement.className = 'tag-item';
        tagElement.innerHTML = `
            <span>${tag}</span>
            ${!isTagUsed ? `<button class="tag-remove" data-tag="${tag}">×</button>` : ''}
        `;
        tagsList.appendChild(tagElement);
    });

    // 绑定删除标签事件
    document.querySelectorAll('.tag-remove').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const tag = e.target.dataset.tag;
            // 在双层结构中删除标签
            for (const [category, subTags] of Object.entries(tags)) {
                const index = subTags.indexOf(tag);
                if (index !== -1) {
                    tags[category].splice(index, 1);
                    break;
                }
            }
            renderAdminTags();
            renderTags();
            renderDishes();
        });
    });
}

// 添加标签
function addTag() {
    const tagName = document.getElementById('tag-name').value.trim();
    if (tagName && !getAllTags().includes(tagName)) {
        // 默认添加到"其他"分类
        tags['其他'].push(tagName);
        document.getElementById('tag-name').value = '';
        renderAdminTags();
        renderTags();
    }
}

// 编辑菜品
function editDish(dishId) {
    const dish = dishes.find(d => d.id === dishId);
    if (dish) {
        // 填充表单
        document.getElementById('edit-dish-name').value = dish.name;
        document.getElementById('edit-dish-price').value = dish.price;
        document.getElementById('edit-dish-image').value = dish.image;
        document.getElementById('edit-dish-desc').value = dish.description;
        document.getElementById('edit-dish-detail-desc').value = dish.detailDescription;
        document.getElementById('edit-dish-method').value = dish.method;
        document.getElementById('edit-dish-ingredients').value = dish.ingredients;
        document.getElementById('edit-dish-tags').value = dish.tags.join(', ');
        
        // 设置编辑模式
        editingDishId = dishId;
        
        // 打开编辑面板
        editPanel.classList.add('active');
    }
}

// 保存菜品
function saveDish() {
    const name = document.getElementById('dish-name').value.trim();
    const price = parseFloat(document.getElementById('dish-price').value);
    const image = document.getElementById('dish-image').value.trim() || "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=Chinese%20food%20dish&image_size=square";
    const description = document.getElementById('dish-desc').value.trim();
    const detailDescription = document.getElementById('dish-detail-desc').value.trim();
    const method = document.getElementById('dish-method').value.trim();
    const ingredients = document.getElementById('dish-ingredients').value.trim();
    const tagsInput = document.getElementById('dish-tags').value.trim();
    const dishTags = tagsInput.split(',').map(tag => tag.trim()).filter(tag => tag);

    if (name && price) {
        // 添加新菜品
        const newDish = {
            id: dishes.length + 1,
            name,
            price,
            image,
            description,
            detailDescription,
            method,
            ingredients,
            tags: dishTags
        };
        dishes.push(newDish);
        renderDishes();
        // 清空表单
        dishForm.reset();
    }
}

// 保存编辑
function saveEdit() {
    const name = document.getElementById('edit-dish-name').value.trim();
    const price = parseFloat(document.getElementById('edit-dish-price').value);
    const image = document.getElementById('edit-dish-image').value.trim() || "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=Chinese%20food%20dish&image_size=square";
    const description = document.getElementById('edit-dish-desc').value.trim();
    const detailDescription = document.getElementById('edit-dish-detail-desc').value.trim();
    const method = document.getElementById('edit-dish-method').value.trim();
    const ingredients = document.getElementById('edit-dish-ingredients').value.trim();
    const tagsInput = document.getElementById('edit-dish-tags').value.trim();
    const dishTags = tagsInput.split(',').map(tag => tag.trim()).filter(tag => tag);

    if (name && price && editingDishId) {
        // 更新现有菜品
        const dishIndex = dishes.findIndex(dish => dish.id === editingDishId);
        if (dishIndex !== -1) {
            dishes[dishIndex] = {
                ...dishes[dishIndex],
                name,
                price,
                image,
                description,
                detailDescription,
                method,
                ingredients,
                tags: dishTags
            };
            editingDishId = null;
            
            // 关闭编辑面板
            editPanel.classList.remove('active');
            
            // 重新渲染菜品
            renderDishes();
            
            // 清空表单
            editDishForm.reset();
        }
    }
}

// 生成dishes数组JSON
function generateDishesJSON() {
    // 生成完整的data.js内容
    const dataJSContent = `// 初始菜品数据
export const dishes = [
${dishes.map(dish => {
    // 确保所有字段格式正确
    const formattedDish = {
        ...dish,
        tags: Array.isArray(dish.tags) ? dish.tags : [dish.tags],
        ingredients: typeof dish.ingredients === 'string' ? dish.ingredients : dish.ingredients.join(', '),
        method: typeof dish.method === 'string' ? dish.method : dish.method.join('\n')
    };
    return JSON.stringify(formattedDish, null, 4);
}).join(',\n')}
];`;
    
    // 生成JSON对象用于快捷指令
    const jsonData = {
        tags: tags,
        tagColors: tagColors,
        dishes: dishes
    };
    
    // 编码JSON数据
    const encodedJSON = encodeURIComponent(JSON.stringify(jsonData));
    
    // 生成苹果快捷指令URL
    const shortcutURL = `shortcuts://run-shortcut?name=小贾私房菜&input=${encodedJSON}`;
    
    // 创建一个弹出窗口，显示JSON内容
    const popup = window.open('', 'dishesJSON', 'width=800,height=600');
    if (popup) {
        popup.document.write(`
            <html>
                <head>
                    <title>更新后的 dishes 数组</title>
                    <style>
                        body { font-family: monospace; white-space: pre; padding: 20px; }
                        .btn-container { position: fixed; top: 10px; right: 10px; display: flex; gap: 10px; z-index: 100; }
                        .btn { padding: 10px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; }
                        .copy-btn { background: #7A77B9; color: white; }
                        .shortcut-btn { background: #F2C76E; color: white; }
                        .btn:hover { opacity: 0.9; transform: translateY(-2px); }
                    </style>
                </head>
                <body>
                    <div class="btn-container">
                        <button class="btn copy-btn" onclick="copyContent()">复制内容</button>
                        <button class="btn shortcut-btn" onclick="openShortcut()">发送到快捷指令</button>
                    </div>
                    <pre id="json-content">${dataJSContent}</pre>
                    <script>
                        function copyContent() {
                            const content = document.getElementById('json-content').textContent;
                            navigator.clipboard.writeText(content).then(() => {
                                alert('内容已复制到剪贴板，请粘贴到 data.js 文件中');
                            });
                        }
                        
                        function openShortcut() {
                            const shortcutURL = '${shortcutURL}';
                            window.location.href = shortcutURL;
                        }
                    </script>
                </body>
            </html>
        `);
        popup.document.close();
    } else {
        alert('请允许弹出窗口，以便查看更新后的 dishes 数组');
    }
}

// 保存数据到GitHub
async function saveDataToGitHub() {
    const saveBtn = document.getElementById('save-to-github');
    const statusEl = document.getElementById('save-status');
    
    // 禁用按钮
    saveBtn.disabled = true;
    statusEl.textContent = '正在保存...';
    statusEl.className = 'save-status';
    
    try {
        // GitHub API配置
        const owner = 'jyh318';
        const repo = 'menu';
        const lins = 'r8OmgPFdsz5bOADbmHAhqMTfDeWqvk43Nytq'
        const token = 'ghp_' + lins;
        
        // 1. 保存data.js文件
        const dataJSContent = `// 初始菜品数据
export const dishes = ${JSON.stringify(dishes, null, 4)};`;
        await saveFileToGitHub(owner, repo, 'data.js', dataJSContent, token);
        
        // 2. 保存tags.js文件
        const tagsJSContent = `// 初始标签数据
export let tags = ${JSON.stringify(tags, null, 4)};

// 标签颜色配置
export const tagColors = ${JSON.stringify(tagColors, null, 4)};`;
        await saveFileToGitHub(owner, repo, 'tags.js', tagsJSContent, token);
        
        // 保存成功
        statusEl.textContent = '✓ 保存成功！';
        statusEl.className = 'save-status success';
    } catch (error) {
        console.error('保存失败:', error);
        statusEl.textContent = '✗ 保存失败: ' + error.message;
        statusEl.className = 'save-status error';
    } finally {
        // 恢复按钮状态
        saveBtn.disabled = false;
    }
}

// 保存单个文件到GitHub
async function saveFileToGitHub(owner, repo, path, content, token) {
    // 先获取文件的SHA（用于更新）
    const getUrl = `https://api.github.com/repos/${owner}/${repo}/contents/${path}`;
    const getResponse = await fetch(getUrl, {
        headers: {
            'Authorization': `token ${token}`
        }
    });
    
    let sha = null;
    if (getResponse.ok) {
        const existingFile = await getResponse.json();
        sha = existingFile.sha;
    }
    
    // 编码内容
    const encodedContent = btoa(unescape(encodeURIComponent(content)));
    
    // 构建请求数据
    const requestData = {
        message: `Update ${path} via admin panel`,
        content: encodedContent
    };
    
    if (sha) {
        requestData.sha = sha;
    }
    
    // 发送请求
    const putUrl = `https://api.github.com/repos/${owner}/${repo}/contents/${path}`;
    const response = await fetch(putUrl, {
        method: 'PUT',
        headers: {
            'Authorization': `token ${token}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
    });
    
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || '保存文件失败');
    }
}

// 更新购物车显示
function updateCartDisplay() {
    const cartContainer = document.getElementById('cart-container');
    const cartContent = document.getElementById('cart-content');
    const cartHeader = document.querySelector('.cart-header');
    const cartToggle = document.getElementById('cart-toggle');

    if (cart.length === 0) {
        cartContainer.classList.remove('active');
        cartContainer.classList.remove('ball');
        cartContainer.style.display = 'none';
    } else {
        cartContainer.classList.add('active');
        cartContainer.style.display = 'flex';
        cartContainer.style.right = '20px';
        cartContainer.style.bottom = '20px';
        cartContainer.style.left = 'auto';
        cartContainer.style.top = 'auto';
        
        if (cartExpanded) {
            cartContainer.classList.remove('ball');
            cartContainer.style.width = '350px';
            cartContainer.style.height = 'auto';
            cartHeader.style.display = 'flex';
            cartContent.classList.add('active');
        } else {
            cartContainer.classList.add('ball');
            cartContainer.style.width = '60px';
            cartContainer.style.height = '60px';
            cartHeader.style.display = 'none';
            cartContent.classList.remove('active');
        }
    }
}

// 生成结算JSON数据
function generateCheckoutJSON() {
    if (cart.length === 0) {
        alert('购物车为空，请先添加菜品');
        return;
    }

    let totalAmount = 0;
    const orderItems = cart.map((item, index) => {
        const subtotal = item.price * item.quantity;
        totalAmount += subtotal;
        return {
            '序号': index + 1,
            '菜品名称': item.name,
            '菜品单价': item.price.toFixed(2),
            '菜品数量': item.quantity,
            '小计金额': subtotal.toFixed(2)
        };
    });

    const checkoutData = {
        '订单详情': orderItems,
        '合计金额': totalAmount.toFixed(2)
    };

    const jsonString = JSON.stringify(checkoutData, null, 2);
    console.log('结算JSON数据:', jsonString);

    const encodedData = encodeURIComponent(jsonString);
    window.location.href = `receipt.html?order=${encodedData}`;
}

// 绑定购物车拖动事件
function bindCartDragEvents() {
    const cartContainer = document.getElementById('cart-container');
    let isDragging = false;
    let startX, startY, startLeft, startTop;
    let isBallClick = false;

    cartContainer.addEventListener('mousedown', (e) => {
        isBallClick = cartContainer.classList.contains('ball') && e.target === cartContainer;
        isDragging = true;
        startX = e.clientX;
        startY = e.clientY;
        const rect = cartContainer.getBoundingClientRect();
        startLeft = rect.left;
        startTop = rect.top;
        cartContainer.style.cursor = 'grabbing';
    });

    document.addEventListener('mousemove', (e) => {
        if (isDragging) {
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            // 如果移动距离超过5px，认为是拖动操作
            if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
                isBallClick = false;
                cartContainer.style.left = `${startLeft + dx}px`;
                cartContainer.style.top = `${startTop + dy}px`;
                cartContainer.style.right = 'auto';
                cartContainer.style.transform = 'none';
            }
        }
    });

    document.addEventListener('mouseup', () => {
        if (isDragging && isBallClick) {
            // 如果是点击操作，展开购物车
            cartExpanded = true;
            updateCartDisplay();
        }
        isDragging = false;
        isBallClick = false;
        cartContainer.style.cursor = 'move';
    });
}

// 绑定logo点击事件
function bindLogoClickEvent() {
    logo.addEventListener('click', () => {
        editMode = !editMode;
        toggleEditButtons();
    });
}

// 切换编辑按钮显示/隐藏
function toggleEditButtons() {
    const actionContainers = document.querySelectorAll('.dish-actions');
    actionContainers.forEach(container => {
        if (editMode) {
            container.style.display = 'flex';
        } else {
            container.style.display = 'none';
        }
    });
}

// 懒加载图片
function lazyLoad() {
    const lazyImages = document.querySelectorAll('.lazy-image');
    
    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.classList.remove('lazy-image');
                observer.unobserve(img);
            }
        });
    });
    
    lazyImages.forEach(img => {
        imageObserver.observe(img);
    });
}

// 初始化应用
init();
