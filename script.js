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

// 初始化
function init() {
    renderTags();
    renderDishes();
    renderCart();
    updateCartDisplay();
    bindEvents();
    bindCartDragEvents();
    bindLogoClickEvent();
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
    cartToggle.addEventListener('click', () => {
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
}

// 渲染标签
function renderTags() {
    tagsWrapper.innerHTML = '';
    tags.forEach(tag => {
        const tagElement = document.createElement('div');
        tagElement.className = `tag ${tag} ${selectedTags.includes(tag) ? 'active' : ''}`;
        tagElement.textContent = tag;
        tagElement.addEventListener('click', () => {
            toggleTag(tag);
        });
        tagsWrapper.appendChild(tagElement);
    });
}

// 切换标签
function toggleTag(tag) {
    if (selectedTags.length === 1 && selectedTags[0] === tag) {
        // 如果点击的是当前选中的标签，取消选择
        selectedTags = [];
    } else {
        // 否则选择该标签
        selectedTags = [tag];
    }
    renderTags();
    renderDishes();
}

// 渲染菜品
function renderDishes() {
    menuGrid.innerHTML = '';
    
    const filteredDishes = dishes.filter(dish => {
        // 标签筛选
        const tagMatch = selectedTags.length === 0 || selectedTags.every(tag => dish.tags.includes(tag));
        // 搜索筛选
        const searchMatch = !searchKeyword || 
            dish.name.toLowerCase().includes(searchKeyword) ||
            dish.description.toLowerCase().includes(searchKeyword) ||
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
}

// 创建菜品卡片
function createDishCard(dish) {
    const card = document.createElement('div');
    card.className = 'dish-card';
    
    card.innerHTML = `
        <div class="dish-image">
            <img src="${dish.image}" alt="${dish.name}" style="width: 100%; height: 100%; object-fit: cover;">
        </div>
        <div class="dish-info">
            <h3 class="dish-name">${dish.name}</h3>
            <div class="dish-price">¥${dish.price.toFixed(2)}</div>
            <p class="dish-desc">${dish.description}</p>
            <div class="dish-tags">
                ${dish.tags.map(tag => `<span class="dish-tag ${tag}">${tag}</span>`).join('')}
            </div>
            <div class="dish-quantity">
                <div class="quantity-control">
                    <button class="quantity-btn decrease" data-id="${dish.id}">-</button>
                    <span class="quantity" data-id="${dish.id}">0</span>
                    <button class="quantity-btn increase" data-id="${dish.id}">+</button>
                </div>
                <button class="edit-dish-btn" data-id="${dish.id}" style="display: none;">编辑</button>
            </div>
        </div>
    `;

    // 点击卡片查看详情
    card.addEventListener('click', (e) => {
        if (!e.target.closest('.quantity-btn') && !e.target.closest('.edit-dish-btn')) {
            showDishDetail(dish);
        }
    });
    
    // 编辑菜品按钮点击事件
    const editBtn = card.querySelector('.edit-dish-btn');
    editBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        editDish(dish.id);
    });

    // 数量控制
    const decreaseBtn = card.querySelector('.decrease');
    const increaseBtn = card.querySelector('.increase');
    const quantitySpan = card.querySelector('.quantity');

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

    return card;
}

// 显示菜品详情
function showDishDetail(dish) {
    dishDetail.innerHTML = `
        <div class="dish-detail-image">
            <img src="${dish.image}" alt="${dish.name}" style="width: 100%; height: 100%; object-fit: cover; border-radius: 15px;">
        </div>
        <h2 class="dish-detail-name">${dish.name}</h2>
        <div class="dish-detail-price">¥${dish.price.toFixed(2)}</div>
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
    tags.forEach(tag => {
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
            tags = tags.filter(t => t !== tag);
            renderAdminTags();
            renderTags();
            renderDishes();
        });
    });
}

// 添加标签
function addTag() {
    const tagName = document.getElementById('tag-name').value.trim();
    if (tagName && !tags.includes(tagName)) {
        tags.push(tagName);
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
            
            // 生成更新后的dishes数组JSON
            generateDishesJSON();
        }
    }
}

// 生成dishes数组JSON
function generateDishesJSON() {
    // 生成完整的data.js内容
    const dataJSContent = `// 初始标签数据
let tags = [
    "炒菜", "炖菜", "卤菜", "红烧", "清蒸", "营养", "丰富", "重口", "清淡", "主食", "健康"
];

// 初始菜品数据
const dishes = [
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
];

// 购物车数据
let cart = [];`;
    
    // 生成JSON对象用于快捷指令
    const jsonData = {
        tags: tags,
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
    const editButtons = document.querySelectorAll('.edit-dish-btn');
    editButtons.forEach(btn => {
        if (editMode) {
            btn.style.display = 'block';
        } else {
            btn.style.display = 'none';
        }
    });
}

// 初始化应用
init();