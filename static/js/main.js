// DaMS - Dungeon Automated Master System
// Frontend JavaScript

const API_URL = '/api';

// DOM Elements
const narrativeLog = document.getElementById('narrative-log');
const actionSuggestions = document.getElementById('action-suggestions');
const actionInput = document.getElementById('action-input');
const sendBtn = document.getElementById('send-btn');
const inventoryList = document.getElementById('inventory-list');
const effectsList = document.getElementById('effects-list');
const locationImage = document.getElementById('location-image');

// Состояние игры
let gameState = {
    location: 'start',  // 'start' или '1', '2', '3' (сеттинг)
    isSettingChoice: false
};

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    addLogEntry('[SYSTEM]', 'DaMS готов. Напиши "начать игру" или нажми на кнопку.', 'system');

    // Генерируем начальную картинку — старый терминал
    updateLocationImage('old cracked computer terminal');

    // Обработчики событий
    sendBtn.addEventListener('click', sendAction);
    actionInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendAction();
    });

    actionSuggestions.addEventListener('click', (e) => {
        if (e.target.classList.contains('action-btn')) {
            const action = e.target.dataset.action;
            if (action) sendAction(action);
        }
    });
});

// Отправка действия
async function sendAction(customAction = null) {
    const action = customAction || actionInput.value.trim();
    if (!action) return;

    // Блокируем ввод на время запроса
    setInteractionEnabled(false);

    // Добавляем действие игрока в лог
    addLogEntry('[ВЫ]', action, 'player');

    try {
        let endpoint = '/action';
        let payload = { action };

        // Поддерживаем русские команды
        if (action === 'start_game' || action === 'начать игру' || action === 'начать') {
            endpoint = '/start';
            payload = {};
            gameState.location = 'start';
            gameState.isSettingChoice = true;
        }
        
        // Обработка выбора сеттинга (1, 2, 3)
        else if (gameState.isSettingChoice && ['1', '2', '3'].includes(action)) {
            endpoint = '/setting';
            payload = { setting: action };
            gameState.isSettingChoice = false;
        }

        const response = await fetch(`${API_URL}${endpoint}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) throw new Error('Ошибка сервера');

        const data = await response.json();

        // Обновляем интерфейс
        updateInterface(data);

    } catch (error) {
        addLogEntry('[ERROR]', `Ошибка: ${error.message}`, 'system');
    } finally {
        setInteractionEnabled(true);
        actionInput.value = '';
        actionInput.focus();
    }
}

// Обновление интерфейса
function updateInterface(data) {
    // Добавляем описание в лог
    addLogEntry('[DaMS]', data.description, 'dams');
    
    // Обновляем кнопки действий
    updateSuggestions(data.suggestions);
    
    // Обновляем инвентарь
    updateInventory(data.inventory);
    
    // Обновляем эффекты
    updateEffects(data.effects);
    
    // Обновляем изображение (если есть prompt)
    if (data.image_prompt) {
        updateLocationImage(data.image_prompt);
    }
}

// Добавление записи в лог
function addLogEntry(sender, text, type = 'dams') {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    
    const timestamp = document.createElement('span');
    timestamp.className = 'timestamp';
    timestamp.textContent = sender;
    
    entry.appendChild(timestamp);
    entry.appendChild(document.createTextNode(text));
    
    narrativeLog.appendChild(entry);
    narrativeLog.scrollTop = narrativeLog.scrollHeight;
}

// Обновление кнопок действий
function updateSuggestions(suggestions) {
    actionSuggestions.innerHTML = '';
    
    if (!suggestions || suggestions.length === 0) return;
    
    suggestions.forEach((suggestion, index) => {
        const btn = document.createElement('button');
        btn.className = 'action-btn';
        btn.textContent = suggestion;
        btn.dataset.action = suggestion;
        actionSuggestions.appendChild(btn);
    });
}

// Обновление инвентаря
function updateInventory(inventory) {
    inventoryList.innerHTML = '';
    
    if (!inventory || inventory.length === 0) {
        inventoryList.innerHTML = '<span class="empty-msg">Пусто</span>';
        return;
    }
    
    inventory.forEach(item => {
        const tag = document.createElement('span');
        tag.className = 'item-tag';
        tag.textContent = item;
        inventoryList.appendChild(tag);
    });
}

// Обновление эффектов
function updateEffects(effects) {
    effectsList.innerHTML = '';
    
    if (!effects || effects.length === 0) {
        effectsList.innerHTML = '<span class="empty-msg">Нет</span>';
        return;
    }
    
    effects.forEach(effect => {
        const tag = document.createElement('span');
        tag.className = 'item-tag';
        tag.textContent = effect;
        effectsList.appendChild(tag);
    });
}

// Обновление изображения локации
function updateLocationImage(prompt) {
    // Запрашиваем картинку через наш сервер (обход CORS)
    const imageUrl = `/api/image?prompt=${encodeURIComponent(prompt)}`;

    locationImage.style.opacity = '0.5';
    locationImage.src = imageUrl;
    locationImage.alt = prompt;

    locationImage.onload = () => {
        locationImage.style.opacity = '1';
    };

    locationImage.onerror = () => {
        console.warn('Не удалось загрузить изображение:', prompt);
        locationImage.src = '';
        locationImage.alt = 'Изображение недоступно';
    };
}

// Включение/выключение интерфейса
function setInteractionEnabled(enabled) {
    actionInput.disabled = !enabled;
    sendBtn.disabled = !enabled;
    
    const buttons = actionSuggestions.querySelectorAll('.action-btn');
    buttons.forEach(btn => {
        btn.disabled = !enabled;
    });
    
    if (enabled) {
        actionInput.focus();
    }
}

// Утилита для добавления системных сообщений
function addSystemMessage(text) {
    addLogEntry('[SYSTEM]', text, 'system');
}
