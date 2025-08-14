// 전역 변수
let currentTheme = 'light';
let isLoading = false;

// DOM 로드 완료 시 초기화
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
    setupEventListeners();
    checkLocalStorage();
});

// 앱 초기화
function initializeApp() {
    console.log('CelebAnalytics 초기화 중...');
    
    // 네비게이션 활성화 상태 설정
    updateActiveNavigation();
    
    // 툴팁 초기화
    initializeTooltips();
    
    // 드롭다운 초기화
    initializeDropdowns();
    
    // 모달 초기화
    initializeModals();
    
    console.log('CelebAnalytics 초기화 완료');
}

// 이벤트 리스너 설정
function setupEventListeners() {
    // 네비게이션 클릭 이벤트
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', handleNavigation);
    });
    
    // 카드 호버 효과
    document.querySelectorAll('.card').forEach(card => {
        card.addEventListener('mouseenter', handleCardHover);
        card.addEventListener('mouseleave', handleCardLeave);
    });
    
    // 검색 기능
    const searchInputs = document.querySelectorAll('.filter-input');
    searchInputs.forEach(input => {
        input.addEventListener('input', debounce(handleSearch, 300));
    });
    
    // 필터 변경 이벤트
    const filterSelects = document.querySelectorAll('.filter-select');
    filterSelects.forEach(select => {
        select.addEventListener('change', handleFilterChange);
    });
    
    // 키보드 단축키
    document.addEventListener('keydown', handleKeyboardShortcuts);
    
    // 스크롤 이벤트
    window.addEventListener('scroll', debounce(handleScroll, 100));
    
    // 리사이즈 이벤트
    window.addEventListener('resize', debounce(handleResize, 250));
}

// 로컬 스토리지 확인 (브라우저 환경에서만)
function checkLocalStorage() {
    try {
        // 사용자 설정 로드
        const savedTheme = localStorage.getItem('celebanalytics_theme');
        if (savedTheme) {
            currentTheme = savedTheme;
            applyTheme(currentTheme);
        }
        
        // 최근 검색어 로드
        const recentSearches = JSON.parse(localStorage.getItem('celebanalytics_recent_searches') || '[]');
        if (recentSearches.length > 0) {
            populateRecentSearches(recentSearches);
        }
    } catch (error) {
        console.log('로컬 스토리지를 사용할 수 없습니다:', error.message);
    }
}

// 네비게이션 처리
function handleNavigation(event) {
    const link = event.currentTarget;
    const href = link.getAttribute('href');
    const target = link.getAttribute('target');

    if (!href || href === '#') {
        return; // 이동할 링크가 없으면 기본 동작
    }

    // 새 탭/새 창 열기 또는 중간 클릭/수정키 클릭은 기본 동작 허용
    const isModifierClick = event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button === 1;
    const isExternal = /^https?:\/\//i.test(href) || target === '_blank';
    if (isModifierClick || isExternal) {
        return; // 기본 동작 그대로 수행
    }

    // 싱글 페이지 내 라우팅이 아니므로 기본 동작을 막고 명시적으로 이동
    event.preventDefault();

    // 현재 경로와 동일하면 중복 이동 방지
    if (window.location.pathname === href) {
        return;
    }

    // 로딩 상태 표시
    showLoadingState();

    // 페이지 전환 애니메이션
    const mainContent = document.querySelector('.main-content');
    if (mainContent) {
        mainContent.style.opacity = '0.7';
        mainContent.style.transform = 'translateY(10px)';
    }

    // 약간의 지연 후 링크로 이동 (로딩 오버레이가 보이도록)
    setTimeout(() => {
        window.location.assign(href);
    }, 50);
}

// 활성 네비게이션 업데이트
function updateActiveNavigation() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav-link');
    
    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href === currentPath || (currentPath === '/' && href === '/')) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
}

// 카드 호버 효과
function handleCardHover(event) {
    const card = event.currentTarget;
    card.style.transform = 'translateY(-5px)';
    card.style.boxShadow = '0 8px 30px rgba(0,0,0,0.15)';
}

function handleCardLeave(event) {
    const card = event.currentTarget;
    card.style.transform = 'translateY(0)';
    card.style.boxShadow = '0 4px 20px rgba(0,0,0,0.1)';
}

// 검색 처리
function handleSearch(event) {
    const query = event.target.value.trim();
    const searchType = event.target.getAttribute('data-search-type') || 'general';
    
    if (query.length < 2) {
        clearSearchResults();
        return;
    }
    
    console.log(`검색 중: "${query}" (타입: ${searchType})`);
    
    // 검색 결과 표시
    showSearchResults(query, searchType);
    
    // 최근 검색어에 추가
    addToRecentSearches(query);
}

// 검색 결과 표시
function showSearchResults(query, type) {
    // 실제 구현에서는 API 호출
    const mockResults = [
        {type: 'celebrity', name: 'IU', score: 95},
        {type: 'keyword', name: '음악', score: 88},
        {type: 'keyword', name: '노래', score: 82}
    ].filter(item => item.name.toLowerCase().includes(query.toLowerCase()));
    
    displaySearchResults(mockResults);
}

// 검색 결과 화면에 표시
function displaySearchResults(results) {
    let resultsContainer = document.getElementById('search-results');
    if (!resultsContainer) {
        resultsContainer = createSearchResultsContainer();
    }
    
    if (results.length === 0) {
        resultsContainer.innerHTML = '<div class="no-results">검색 결과가 없습니다.</div>';
        return;
    }
    
    resultsContainer.innerHTML = results.map(result => `
        <div class="search-result-item" onclick="selectSearchResult('${result.type}', '${result.name}')">
            <div class="result-icon">
                <i class="fas fa-${result.type === 'celebrity' ? 'star' : 'tag'}"></i>
            </div>
            <div class="result-content">
                <div class="result-name">${result.name}</div>
                <div class="result-type">${result.type === 'celebrity' ? '연예인' : '키워드'}</div>
            </div>
            <div class="result-score">${result.score}%</div>
        </div>
    `).join('');
}

// 검색 결과 컨테이너 생성
function createSearchResultsContainer() {
    const container = document.createElement('div');
    container.id = 'search-results';
    container.className = 'search-results';
    container.style.cssText = `
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        background: white;
        border: 1px solid #e9ecef;
        border-radius: 6px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        max-height: 300px;
        overflow-y: auto;
        z-index: 1000;
        display: none;
    `;
    
    // 검색 입력 필드의 부모에 추가
    const searchInput = document.querySelector('.filter-input');
    if (searchInput && searchInput.parentElement) {
        searchInput.parentElement.style.position = 'relative';
        searchInput.parentElement.appendChild(container);
    }
    
    return container;
}

// 검색 결과 선택
function selectSearchResult(type, name) {
    if (type === 'celebrity') {
        window.location.href = `/dashboard?name=${encodeURIComponent(name)}`;
    } else if (type === 'keyword') {
        window.location.href = `/dashboard?search=${encodeURIComponent(name)}`;
    }
}

// 검색 결과 초기화
function clearSearchResults() {
    const resultsContainer = document.getElementById('search-results');
    if (resultsContainer) {
        resultsContainer.style.display = 'none';
    }
}

// 최근 검색어에 추가
function addToRecentSearches(query) {
    try {
        let recentSearches = JSON.parse(localStorage.getItem('celebanalytics_recent_searches') || '[]');
        
        // 중복 제거
        recentSearches = recentSearches.filter(search => search !== query);
        
        // 새 검색어를 맨 앞에 추가
        recentSearches.unshift(query);
        
        // 최대 10개까지만 저장
        recentSearches = recentSearches.slice(0, 10);
        
        localStorage.setItem('celebanalytics_recent_searches', JSON.stringify(recentSearches));
    } catch (error) {
        console.log('최근 검색어 저장 실패:', error.message);
    }
}

// 필터 변경 처리
function handleFilterChange(event) {
    const filter = event.target;
    const filterType = filter.getAttribute('data-filter-type') || filter.id;
    const value = filter.value;
    
    console.log(`필터 변경: ${filterType} = ${value}`);
    
    // 필터 적용 애니메이션
    showLoadingState();
    
    // 실제 필터링 로직 (API 호출 등)
    setTimeout(() => {
        hideLoadingState();
        showFilterNotification(`${filterType} 필터가 적용되었습니다.`);
    }, 1000);
}

// 키보드 단축키 처리
function handleKeyboardShortcuts(event) {
    // Ctrl/Cmd + K: 검색 포커스
    if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
        event.preventDefault();
        const searchInput = document.querySelector('.filter-input');
        if (searchInput) {
            searchInput.focus();
        }
    }
    
    // ESC: 검색 결과 닫기
    if (event.key === 'Escape') {
        clearSearchResults();
    }
}

// 스크롤 처리
function handleScroll() {
    const navbar = document.querySelector('.navbar');
    if (navbar) {
        if (window.scrollY > 50) {
            navbar.style.boxShadow = '0 4px 20px rgba(0,0,0,0.15)';
        } else {
            navbar.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
        }
    }
    
    // 스크롤 위치에 따른 애니메이션
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => {
        const rect = card.getBoundingClientRect();
        const isVisible = rect.top < window.innerHeight && rect.bottom > 0;
        
        if (isVisible && !card.classList.contains('animated')) {
            card.classList.add('animated', 'fade-in');
        }
    });
}

// 리사이즈 처리
function handleResize() {
    // 차트 리사이즈는 Chart.js가 자동으로 처리
    
    // 모바일 네비게이션 처리
    const navMenu = document.querySelector('.nav-menu');
    if (navMenu && window.innerWidth < 768) {
        navMenu.classList.add('mobile-nav');
    } else if (navMenu) {
        navMenu.classList.remove('mobile-nav');
    }
}

// 툴팁 초기화
function initializeTooltips() {
    const tooltipElements = document.querySelectorAll('[data-tooltip]');
    tooltipElements.forEach(element => {
        element.addEventListener('mouseenter', showTooltip);
        element.addEventListener('mouseleave', hideTooltip);
    });
}

// 툴팁 표시
function showTooltip(event) {
    const element = event.currentTarget;
    const text = element.getAttribute('data-tooltip');
    
    const tooltip = document.createElement('div');
    tooltip.className = 'tooltip';
    tooltip.textContent = text;
    tooltip.style.cssText = `
        position: absolute;
        background: #333;
        color: white;
        padding: 0.5rem;
        border-radius: 4px;
        font-size: 0.875rem;
        z-index: 9999;
        pointer-events: none;
        white-space: nowrap;
    `;
    
    document.body.appendChild(tooltip);
    
    const rect = element.getBoundingClientRect();
    tooltip.style.top = (rect.top - tooltip.offsetHeight - 5) + 'px';
    tooltip.style.left = (rect.left + rect.width / 2 - tooltip.offsetWidth / 2) + 'px';
    
    element._tooltip = tooltip;
}

// 툴팁 숨기기
function hideTooltip(event) {
    const element = event.currentTarget;
    if (element._tooltip) {
        element._tooltip.remove();
        delete element._tooltip;
    }
}

// 드롭다운 초기화
function initializeDropdowns() {
    const dropdowns = document.querySelectorAll('.dropdown');
    dropdowns.forEach(dropdown => {
        const toggle = dropdown.querySelector('.dropdown-toggle');
        const menu = dropdown.querySelector('.dropdown-menu');
        
        if (toggle && menu) {
            toggle.addEventListener('click', () => toggleDropdown(dropdown));
            
            // 외부 클릭 시 닫기
            document.addEventListener('click', (event) => {
                if (!dropdown.contains(event.target)) {
                    dropdown.classList.remove('active');
                }
            });
        }
    });
}

// 드롭다운 토글
function toggleDropdown(dropdown) {
    dropdown.classList.toggle('active');
}

// 모달 초기화
function initializeModals() {
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => {
        const closeBtn = modal.querySelector('.modal-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => closeModal(modal));
        }
        
        // 배경 클릭 시 닫기
        modal.addEventListener('click', (event) => {
            if (event.target === modal) {
                closeModal(modal);
            }
        });
    });
}

// 모달 열기
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

// 모달 닫기
function closeModal(modal) {
    modal.classList.remove('active');
    document.body.style.overflow = '';
}

// 로딩 상태 표시
function showLoadingState() {
    if (isLoading) return;
    
    isLoading = true;
    const loading = document.createElement('div');
    loading.id = 'global-loading';
    loading.innerHTML = `
        <div class="loading-backdrop">
            <div class="loading-spinner">
                <div class="spinner"></div>
                <div>로딩 중...</div>
            </div>
        </div>
    `;
    loading.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 9999;
    `;
    
    document.body.appendChild(loading);
}

// 로딩 상태 숨기기
function hideLoadingState() {
    isLoading = false;
    const loading = document.getElementById('global-loading');
    if (loading) {
        loading.remove();
    }
}

// 필터 알림 표시
function showFilterNotification(message) {
    const notification = document.createElement('div');
    notification.className = 'filter-notification';
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 100px;
        right: 20px;
        background: #28a745;
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 6px;
        z-index: 9999;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        animation: slideInRight 0.3s ease;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// 테마 적용
function applyTheme(theme) {
    document.body.className = theme === 'dark' ? 'dark-theme' : '';
    currentTheme = theme;
    
    try {
        localStorage.setItem('celebanalytics_theme', theme);
    } catch (error) {
        console.log('테마 저장 실패:', error.message);
    }
}

// 테마 토글
function toggleTheme() {
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    applyTheme(newTheme);
}

// 디바운스 함수
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 유틸리티 함수들
const Utils = {
    // 숫자 포맷팅
    formatNumber: (num) => {
        if (num >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'K';
        }
        return num.toLocaleString();
    },
    
    // 날짜 포맷팅
    formatDate: (date) => {
        return new Date(date).toLocaleDateString('ko-KR', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    },
    
    // 퍼센트 포맷팅
    formatPercent: (value, decimals = 1) => {
        return value.toFixed(decimals) + '%';
    },
    
    // 색상 생성
    generateColor: (opacity = 1) => {
        const colors = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe', '#00f2fe'];
        const randomColor = colors[Math.floor(Math.random() * colors.length)];
        return opacity < 1 ? randomColor.replace(')', `, ${opacity})`) : randomColor;
    }
};

// 전역 객체로 내보내기
window.CelebAnalytics = {
    openModal,
    closeModal,
    toggleTheme,
    showLoadingState,
    hideLoadingState,
    Utils
};