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

// 状态变量
let selectedTags = [];
let searchKeyword = '';
let cartVisible = false;
let cartExpanded = false;

// 初始化
function init() {
    renderTags();
    renderDishes();
    renderCart();
    updateCartDisplay();
    bindEvents();
    bindCartDragEvents();
}

// 绑定事件
function bindEvents() {
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
        tagElement.className = `tag ${selectedTags.includes(tag) ? 'active' : ''}`;
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
                ${dish.tags.map(tag => `<span class="dish-tag">${tag}</span>`).join('')}
            </div>
            <div class="dish-quantity">
                <div class="quantity-control">
                    <button class="quantity-btn decrease" data-id="${dish.id}">-</button>
                    <span class="quantity" data-id="${dish.id}">0</span>
                    <button class="quantity-btn increase" data-id="${dish.id}">+</button>
                </div>
            </div>
        </div>
    `;

    // 点击卡片查看详情
    card.addEventListener('click', (e) => {
        if (!e.target.closest('.quantity-btn')) {
            showDishDetail(dish);
        }
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

// 初始化应用
init();