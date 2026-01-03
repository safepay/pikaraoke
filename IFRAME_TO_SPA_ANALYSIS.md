# PiKaraoke: Iframe to SPA Migration Analysis

**Date:** 2026-01-03
**Branch:** claude/analyze-iframe-migration-Rjfvk

---

## Executive Summary

This document analyzes the current PiKaraoke architecture and provides recommendations for migrating from an iframe-based menu system to a single-page architecture (SPA) using DIV elements while maintaining full HTML rendering from the backend.

### Key Findings:
- **Limited iframe usage**: Only used for splash screen menu overlay (not site-wide navigation)
- **Current tech stack**: jQuery 3.3.1 + Socket.IO + traditional server-rendered templates
- **Modernization opportunity**: Fetch API is a viable jQuery replacement, but jQuery is still functional
- **Socket.io complexity**: Requires careful state management during SPA transitions
- **Migration scope**: Moderate effort (~15-20 files to modify)

---

## 1. Current Architecture Overview

### 1.1 Technology Stack

| Component | Technology | Version | Usage |
|-----------|-----------|---------|--------|
| Frontend Framework | jQuery | 3.3.1 | DOM manipulation, AJAX |
| Real-time Comms | Socket.IO | 4.x | Live updates, playback control |
| UI Framework | Bulma CSS | Latest | Styling, responsive layout |
| Utilities | Lodash | Latest | debounce(), isEqual() |
| Template Engine | Jinja2 | Latest | Server-side rendering |
| Backend | Flask | Latest | Web framework |
| UI Components | Selectize.js | Latest | Autocomplete dropdowns |

### 1.2 Page Structure

```
base.html (master template)
├── home.html - Now playing + admin controls
├── queue.html - Song queue management
├── search.html - YouTube search + local autocomplete
├── files.html - Browse local songs
├── edit.html - Song rename/cleanup
├── info.html - System information
└── splash.html - Full-screen video display + iframe menu
```

### 1.3 Navigation Patterns

**Traditional Navigation (Most Pages):**
- Standard `<a href>` links in navbar
- Full page reload on navigation
- Server renders complete HTML

**Iframe Navigation (Splash Screen Only):**
```javascript
// splash.html lines 493-511
$('#menu a').click(function () {
  if (showMenu) {
    $('#menu-container').hide();
    $('#menu-container iframe').attr('src', '');  // Clear
    showMenu = false;
  } else {
    $("#menu-container iframe").attr("src", "/");  // Load home
    showMenu = true;
  }
});
```

**AJAX Navigation (Some Actions):**
- Queue operations (add/delete/reorder)
- Playback controls (skip/pause/volume)
- Search autocomplete
- Real-time status updates

---

## 2. Iframe Usage Analysis

### 2.1 Current Implementation

**Location:** `splash.html:762-765, 907-910`

**Purpose:** Menu overlay on splash screen (full-screen video display)

**HTML Structure:**
```html
<div id="menu-background" class="overlay"></div>
<div id="menu-container" class="">
  <iframe></iframe>  <!-- 600px wide, 75vh tall -->
</div>
```

**Why It's Used:**
- Splash screen is a specialized full-screen display for video playback
- Needs menu access without leaving the video view
- Iframe provides complete navigation isolation
- Prevents splash screen JavaScript from interfering with menu pages

### 2.2 Iframe Limitations

1. **Performance:** Additional HTTP request + full page render in iframe
2. **Memory:** Separate DOM tree and JavaScript context
3. **Complexity:** Cookie handling, socket connections duplicated
4. **User Experience:** Nested scrolling, focus management issues
5. **Mobile:** Iframe rendering can be problematic on some devices
6. **Testing:** Harder to test iframe content programmatically

### 2.3 Pages Loaded in Iframe

The iframe loads `"/"` (home.html), which contains the standard navbar:
- Home
- Queue
- Search
- Browse
- Info

User can navigate within the iframe to any of these pages.

---

## 3. Ajax vs Modern Alternatives

### 3.1 Current jQuery AJAX Patterns

**Pattern 1: Simple GET (most common)**
```javascript
// home.html:89, 102, 109, etc.
$.get("/volume/" + value);
$.get("/transpose/" + value);
$.get("/skip");
```

**Pattern 2: GET with Callback**
```javascript
// queue.html:9-18
$.get('{{ url_for("queue.get_queue") }}', function (data) {
  newQueue = JSON.parse(data);
  if (!_.isEqual(newQueue, previousQueue)) {
    queue = newQueue;
    $("#auto-refresh").html(generateQueueHTML());
  }
});
```

**Pattern 3: POST with Form Data**
```javascript
// search.html:305-328
$.ajax({
  url: "{{ url_for('queue.enqueue') }}",
  type: "post",
  data: $("#queue-form").serialize(),
  success: function (data) {
    var obj = JSON.parse(data);
    showNotification("Added song: " + obj.song, "is-success");
  }
});
```

**Pattern 4: Autocomplete (Streaming)**
```javascript
// search.html:265-274
load: function (query, callback) {
  $.ajax({
    url: "{{ url_for('search.autocomplete') }}" + "?q=" + query,
    type: "get",
    success: function (data) {
      callback(data);
    }
  });
}
```

### 3.2 Modern Fetch API Alternative

**Browser Support:** 97%+ (all modern browsers, IE11 needs polyfill)

**Equivalent Patterns:**

```javascript
// Pattern 1: Simple GET
fetch("/volume/" + value);

// Pattern 2: GET with JSON parsing
fetch('/queue/get_queue')
  .then(response => response.json())
  .then(newQueue => {
    if (!_.isEqual(newQueue, previousQueue)) {
      queue = newQueue;
      $("#auto-refresh").html(generateQueueHTML());
    }
  });

// Pattern 3: POST with Form Data
fetch('/queue/enqueue', {
  method: 'POST',
  body: new FormData(document.getElementById('queue-form'))
})
  .then(response => response.json())
  .then(obj => {
    showNotification("Added song: " + obj.song, "is-success");
  });

// Pattern 4: Autocomplete
fetch('/search/autocomplete?q=' + query)
  .then(response => response.json())
  .then(data => callback(data));
```

### 3.3 Axios Alternative

**Why consider it:** More user-friendly API, automatic JSON parsing, better error handling

```javascript
// Pattern 2 with Axios (cleaner)
const { data: newQueue } = await axios.get('/queue/get_queue');
if (!_.isEqual(newQueue, previousQueue)) {
  queue = newQueue;
  $("#auto-refresh").html(generateQueueHTML());
}

// Pattern 3 with Axios
const { data: obj } = await axios.post('/queue/enqueue',
  new FormData(document.getElementById('queue-form'))
);
showNotification("Added song: " + obj.song, "is-success");
```

### 3.4 Recommendation: Fetch API

**Rationale:**
1. **Native browser support** - No additional library needed
2. **Standards-based** - Won't become deprecated
3. **Minimal migration effort** - Pattern conversion is straightforward
4. **Size reduction** - jQuery is 30KB minified, Fetch is built-in
5. **Modern promise-based** - Better error handling, async/await support
6. **jQuery removal** - Still need to replace DOM manipulation (~80% of usage)

**Alternative: Keep jQuery for now**
- jQuery still works perfectly fine
- Would require replacing ALL jQuery usage (DOM + AJAX)
- Adds significant migration scope
- **Recommendation: Defer jQuery removal to separate initiative**

---

## 4. Socket.IO Management Considerations

### 4.1 Current Socket.IO Architecture

**Initialization (Duplicated on Each Page):**

```javascript
// base.html:41-48 & splash.html:38-48
var socket = io();

function connectSocket() {
  socket = io();
  socket.on('connect', function() {
    console.log('Socket connected');
  });
  socket.on('disconnect', function() {
    console.log('Socket disconnected');
  });
}
```

**Event Handlers by Page:**

| Page | Events Listened | Purpose |
|------|----------------|---------|
| splash.html | `now_playing`, `pause`, `play`, `skip`, `volume`, `restart`, `notification` | Video playback control |
| home.html | `now_playing` | Control panel updates |
| queue.html | `queue_update` | Live queue changes |

**Backend Broadcast Events:**
```python
# lib/current_app.py:58-66
def broadcast_event(event: str, data: Any = None) -> None:
  emit(event, data, namespace="/", broadcast=True)
```

**Critical Events:**
- `now_playing` - Current song state (broadcasted to ALL clients)
- `queue_update` - Queue modified (broadcasted to ALL clients)
- `pause/play/skip/restart/volume` - Playback controls (broadcasted to ALL clients)
- `notification` - User notifications (broadcasted to ALL clients)

### 4.2 SPA Socket.IO Challenges

**Challenge 1: Event Handler Cleanup**
- Current: Each page load creates new socket connection
- Problem: SPA navigation doesn't reload page
- Solution: Must manually unbind old event handlers before binding new ones

**Challenge 2: Connection State Management**
- Current: Global `socket` variable per page
- Problem: Need single persistent connection across views
- Solution: Singleton socket manager with view-specific handler registration

**Challenge 3: Memory Leaks**
- Current: Page unload cleans up automatically
- Problem: SPA keeps handlers in memory after view change
- Solution: Explicit cleanup on view unmount

**Challenge 4: Reconnection Logic**
```javascript
// splash.html:613-621 (duplicated on multiple pages)
document.addEventListener("visibilitychange", function() {
  if (document.visibilityState === 'visible') {
    loadNowPlaying();
    if (!socket.connected) {
      console.log('Reconnecting socket...');
      connectSocket();
    }
  }
});
```
- Solution: Centralized reconnection handler

### 4.3 Recommended Socket.IO Architecture for SPA

**Singleton Socket Manager (New File: `socket-manager.js`):**

```javascript
class SocketManager {
  constructor() {
    if (SocketManager.instance) {
      return SocketManager.instance;
    }

    this.socket = io();
    this.eventHandlers = new Map(); // view -> {event -> handler}
    this.globalHandlers = new Map(); // event -> handler (always active)

    this.socket.on('connect', () => console.log('Socket connected'));
    this.socket.on('disconnect', () => console.log('Socket disconnected'));

    // Auto-reconnect on visibility change
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === 'visible' && !this.socket.connected) {
        console.log('Reconnecting socket...');
        this.socket.connect();
      }
    });

    SocketManager.instance = this;
  }

  // Register global handler (never removed)
  onGlobal(event, handler) {
    this.globalHandlers.set(event, handler);
    this.socket.on(event, handler);
  }

  // Register view-specific handler
  on(viewName, event, handler) {
    if (!this.eventHandlers.has(viewName)) {
      this.eventHandlers.set(viewName, new Map());
    }
    this.eventHandlers.get(viewName).set(event, handler);
    this.socket.on(event, handler);
  }

  // Cleanup handlers for a view
  cleanup(viewName) {
    const handlers = this.eventHandlers.get(viewName);
    if (handlers) {
      handlers.forEach((handler, event) => {
        this.socket.off(event, handler);
      });
      this.eventHandlers.delete(viewName);
    }
  }

  emit(event, data) {
    this.socket.emit(event, data);
  }
}

// Singleton instance
const socketManager = new SocketManager();
```

**Usage in SPA Views:**

```javascript
// When loading "queue" view
function loadQueueView() {
  // Cleanup previous view
  socketManager.cleanup('queue');

  // Register new handlers
  socketManager.on('queue', 'queue_update', getQueue);

  // Initial load
  getQueue();
}

// When leaving "queue" view
function unloadQueueView() {
  socketManager.cleanup('queue');
}
```

**Global Handlers (Never Cleaned Up):**
```javascript
// In base initialization
socketManager.onGlobal('notification', (data) => {
  const [message, categoryClass = "is-primary"] = data.split("::");
  showNotification(message, categoryClass);
});
```

---

## 5. Migration Strategy Options

### Option A: Full SPA with Client-Side Routing

**Architecture:**
- Single `index.html` loaded once
- JavaScript router (e.g., History API)
- Fetch HTML fragments from server
- Insert into content DIV
- Manage socket handlers per view

**Pros:**
- True single-page experience
- No page reloads
- Smooth transitions
- Browser back/forward works

**Cons:**
- Moderate JavaScript complexity
- Need router library or custom implementation
- More extensive testing required
- Affects all pages

**Estimated Effort:** 3-4 days

---

### Option B: Hybrid SPA (Recommended)

**Architecture:**
- Keep traditional navigation for main pages (home, queue, search, browse, info)
- Convert ONLY the splash screen iframe to DIV-based overlay
- Fetch menu content dynamically without iframe
- Maintain existing socket architecture per page

**Pros:**
- Minimal scope - only affects splash.html
- Low risk - existing pages unchanged
- Solves iframe performance issues
- Easy to test and rollback
- Existing socket handlers work as-is

**Cons:**
- Still have page reloads for main navigation
- Doesn't modernize entire app

**Estimated Effort:** 0.5-1 day

---

### Option C: Progressive Enhancement SPA

**Architecture:**
- Start with Option B (fix splash iframe)
- Gradually convert individual pages to SPA views
- Use feature flags to toggle SPA vs traditional
- Complete migration over multiple releases

**Pros:**
- Incremental migration
- Can pause/resume at any time
- Lower risk per release
- Learn and adapt as you go

**Cons:**
- Longer overall timeline
- Mixed architecture during transition
- Need to maintain both patterns

**Estimated Effort:** 1-2 days initial, then ongoing

---

## 6. Detailed Migration Plan (Option B - Recommended)

### 6.1 Changes Required

**File: `splash.html`**

**Current iframe approach (lines 762-765, 493-511):**
```html
<div id="menu-background" class="overlay"></div>
<div id="menu-container" class="">
  <iframe></iframe>
</div>
```
```javascript
$('#menu a').click(function () {
  if (showMenu) {
    $('#menu-container').hide();
    $('#menu-container iframe').attr('src', '');
    showMenu = false;
  } else {
    $("#menu-container iframe").attr("src", "/");
    showMenu = true;
  }
});
```

**New DIV approach:**
```html
<div id="menu-background" class="overlay"></div>
<div id="menu-container" class="">
  <div id="menu-content"></div>  <!-- Replace iframe with div -->
</div>
```
```javascript
$('#menu a').click(function () {
  if (showMenu) {
    $('#menu-container').hide();
    $('#menu-content').html('');  // Clear content
    showMenu = false;
  } else {
    setUserCookie();
    $("#menu-container").show();
    loadMenuContent();  // NEW FUNCTION
    showMenu = true;
  }
});

// NEW FUNCTION
function loadMenuContent() {
  $.get('/', function(html) {
    // Extract just the content we need (skip duplicate navbar in iframe)
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const content = doc.querySelector('.box');  // Main content box

    $('#menu-content').html(content.innerHTML);

    // Re-initialize any scripts for the loaded content
    initializeMenuScripts();
  });
}

// NEW FUNCTION - Initialize dynamic content handlers
function initializeMenuScripts() {
  // Reload now playing data
  if (typeof loadNowPlaying === 'function') {
    loadNowPlaying();
  }

  // Attach click handlers for navigation links
  $('#menu-content a.navbar-item').on('click', function(e) {
    e.preventDefault();
    const url = $(this).attr('href');
    loadMenuPage(url);
  });
}

// NEW FUNCTION - Load different pages in menu
function loadMenuPage(url) {
  $.get(url, function(html) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const content = doc.querySelector('.box');

    $('#menu-content').html(content.innerHTML);

    // Re-run page-specific initialization
    runPageInitialization(url);
  });
}

// NEW FUNCTION - Run page-specific code
function runPageInitialization(url) {
  // Call page-specific init based on URL
  if (url.includes('/queue')) {
    initializeQueuePage();
  } else if (url.includes('/search')) {
    initializeSearchPage();
  }
  // etc.
}
```

**CSS Changes (splash.html lines 907-910):**
```css
/* OLD */
#menu-container iframe {
  width: 600px;
  height: 75vh;
}

/* NEW */
#menu-container #menu-content {
  width: 600px;
  height: 75vh;
  overflow-y: auto;  /* Enable scrolling */
  background-color: #363636;  /* Match theme */
  padding: 10px;
}
```

### 6.2 Socket.IO Considerations

**Problem:** Pages loaded into menu DIV have their own socket initialization code

**Solution 1: Simple (Recommended for Option B)**
- Extract socket initialization scripts from loaded HTML
- Don't execute them (menu uses parent page socket)
- Menu content shares splash.html socket connection

**Solution 2: Shared Socket**
- Modify templates to check if socket already exists
```javascript
// In base.html, change from:
var socket = io();

// To:
if (typeof socket === 'undefined') {
  var socket = io();
}
```

### 6.3 Template Refactoring

**Create new endpoint for menu content:**

```python
# routes/menu.py (NEW FILE)
from flask import Blueprint, render_template

menu_bp = Blueprint('menu', __name__)

@menu_bp.route('/menu/<page>')
def menu_page(page):
    """Return page content without base template for menu loading"""
    # Map page names to templates
    templates = {
        'home': 'home.html',
        'queue': 'queue.html',
        'search': 'search.html',
        'browse': 'files.html',
        'info': 'info.html'
    }

    if page in templates:
        # Return only content block, not full page
        return render_template(
            templates[page],
            menu_mode=True  # Flag to skip base template
        )
    return "Page not found", 404
```

**Then in splash.html:**
```javascript
function loadMenuContent() {
  $.get('/menu/home', function(html) {
    $('#menu-content').html(html);
    initializeMenuScripts();
  });
}
```

### 6.4 Testing Checklist

- [ ] Menu opens and displays home page content
- [ ] Navigation within menu works (home, queue, search, browse, info)
- [ ] Menu closes properly
- [ ] Click outside menu closes it
- [ ] Socket events still work (now playing updates)
- [ ] Volume/playback controls work in menu
- [ ] Queue operations work in menu
- [ ] Search autocomplete works in menu
- [ ] User cookie is set properly
- [ ] No JavaScript errors in console
- [ ] Mobile responsive (menu size)
- [ ] Browser back/forward don't break menu
- [ ] Memory: No leaks on repeated open/close

---

## 7. Alternative: Full SPA Migration (Option A)

If you decide to do full SPA migration later, here's the approach:

### 7.1 New Architecture

```
index.html (shell)
├── #/home → fetch /api/home → insert into #app
├── #/queue → fetch /api/queue → insert into #app
├── #/search → fetch /api/search → insert into #app
└── #/browse → fetch /api/browse → insert into #app
```

### 7.2 Router Implementation

**Simple History API Router:**

```javascript
class Router {
  constructor(routes) {
    this.routes = routes;
    this.currentView = null;

    // Handle browser back/forward
    window.addEventListener('popstate', (e) => {
      this.navigate(e.state?.path || '/', false);
    });

    // Intercept link clicks
    document.addEventListener('click', (e) => {
      if (e.target.matches('a[data-spa-link]')) {
        e.preventDefault();
        this.navigate(e.target.getAttribute('href'));
      }
    });
  }

  async navigate(path, pushState = true) {
    // Find matching route
    const route = this.routes.find(r => r.path === path);
    if (!route) {
      console.error('Route not found:', path);
      return;
    }

    // Cleanup previous view
    if (this.currentView?.cleanup) {
      this.currentView.cleanup();
    }

    // Update browser history
    if (pushState) {
      history.pushState({ path }, '', path);
    }

    // Fetch new content
    const html = await fetch(route.endpoint).then(r => r.text());

    // Update content
    document.getElementById('app').innerHTML = html;

    // Run view initialization
    if (route.init) {
      this.currentView = route.init();
    }
  }
}

// Define routes
const router = new Router([
  {
    path: '/',
    endpoint: '/api/home',
    init: () => {
      loadNowPlaying();
      const cleanup = () => socketManager.cleanup('home');
      socketManager.on('home', 'now_playing', handleNowPlaying);
      return { cleanup };
    }
  },
  {
    path: '/queue',
    endpoint: '/api/queue',
    init: () => {
      getQueue();
      const cleanup = () => socketManager.cleanup('queue');
      socketManager.on('queue', 'queue_update', getQueue);
      return { cleanup };
    }
  },
  // ... more routes
]);

// Initial navigation
router.navigate(window.location.pathname, false);
```

### 7.3 Backend API Endpoints

```python
# routes/api.py (NEW FILE)
from flask import Blueprint, render_template

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/home')
def home():
    """Return home page content only (no base template)"""
    return render_template('home_content.html', admin=is_admin())

@api_bp.route('/queue')
def queue():
    """Return queue page content only"""
    return render_template('queue_content.html', admin=is_admin())

# ... etc
```

### 7.4 Template Refactoring for SPA

**Current structure:**
```
base.html (navbar + scripts)
  └── home.html (extends base, fills content block)
```

**New structure:**
```
index.html (navbar + #app container + scripts)
home_content.html (just content, no base extension)
queue_content.html (just content, no base extension)
```

**index.html:**
```html
<!DOCTYPE html>
<html>
<head>
  <!-- All scripts, styles from base.html -->
  <script src="/static/socket-manager.js"></script>
  <script src="/static/router.js"></script>
</head>
<body>
  <nav class="navbar">
    <!-- Navigation links with data-spa-link -->
    <a href="/" data-spa-link>Home</a>
    <a href="/queue" data-spa-link>Queue</a>
    <!-- etc -->
  </nav>

  <div id="app">
    <!-- Content loaded here -->
  </div>

  <script>
    // Initialize router
    const router = new Router([...]);
  </script>
</body>
</html>
```

---

## 8. Comparison Matrix

| Aspect | Current (Iframe) | Option A (Full SPA) | Option B (Hybrid) |
|--------|------------------|---------------------|-------------------|
| **Scope** | N/A | All pages | Splash screen only |
| **Effort** | N/A | 3-4 days | 0.5-1 day |
| **Risk** | N/A | High | Low |
| **Performance** | Slow (iframe overhead) | Fast | Better |
| **Complexity** | Low | High | Low |
| **Socket Management** | Per-page | Centralized | Per-page |
| **Testing** | Easy | Extensive | Moderate |
| **Rollback** | N/A | Difficult | Easy |
| **Browser Compat** | Excellent | Good (IE11 needs polyfill) | Excellent |
| **Mobile** | Issues | Good | Good |
| **Future Proof** | No | Yes | Partial |

---

## 9. Recommendations

### Primary Recommendation: Option B (Hybrid SPA)

**Rationale:**
1. **Solves the immediate problem** - Removes iframe from splash screen
2. **Low risk** - Only affects one page, easy to test and rollback
3. **Quick implementation** - Can be done in 0.5-1 day
4. **Keeps working architecture** - Doesn't change socket handling on other pages
5. **Foundation for future** - Can expand to full SPA later if desired

**Implementation Priority:**
1. ✅ Create `/menu/<page>` API endpoint for content-only rendering
2. ✅ Replace iframe with DIV in splash.html
3. ✅ Implement `loadMenuContent()` function using jQuery $.get()
4. ✅ Add navigation handler for menu links
5. ✅ Add CSS for menu-content DIV
6. ✅ Test thoroughly on splash screen
7. ✅ Deploy and monitor

### Secondary Recommendation: Keep jQuery, Defer to Fetch Migration

**Rationale:**
1. **jQuery works fine** - No bugs, performance is acceptable
2. **Fetch migration is separate concern** - Can be done independently
3. **DOM manipulation dependency** - Would need to replace all jQuery, not just AJAX
4. **Risk vs Reward** - Low benefit for high effort
5. **Bundle size** - 30KB is acceptable for this use case

**If you must migrate to Fetch:**
- Do it as a separate initiative AFTER SPA migration
- Create helper functions to match jQuery patterns:
  ```javascript
  // Helper to match $.get() simplicity
  async function get(url, callback) {
    const response = await fetch(url);
    const data = await response.text();
    if (callback) callback(data);
    return data;
  }

  async function getJSON(url, callback) {
    const response = await fetch(url);
    const data = await response.json();
    if (callback) callback(data);
    return data;
  }
  ```
- Replace jQuery DOM manipulation with vanilla JS:
  ```javascript
  // jQuery
  $("#element").html(content);
  $("#element").show();
  $("#element").addClass("active");

  // Vanilla JS
  document.getElementById("element").innerHTML = content;
  document.getElementById("element").style.display = "block";
  document.getElementById("element").classList.add("active");
  ```

### Future Consideration: Full SPA (Option A)

**When to consider:**
- User feedback indicates slow page loads
- Want to add page transition animations
- Need offline/PWA capabilities
- Planning major UI overhaul anyway

**Prerequisites before attempting:**
1. Complete Option B migration first
2. Add comprehensive integration tests
3. Create feature flag system for gradual rollout
4. Budget 3-4 days development + 2-3 days testing

---

## 10. Socket.IO Best Practices for SPA

Regardless of which option you choose, follow these best practices:

### 10.1 Single Socket Connection
```javascript
// Don't create multiple sockets
// ❌ BAD
function initPage() {
  var socket = io();  // Creates new connection
}

// ✅ GOOD
const socket = io();  // One global connection
function initPage() {
  // Use existing socket
}
```

### 10.2 Clean Up Event Handlers
```javascript
// ❌ BAD - Handlers stack up on each view change
function loadQueueView() {
  socket.on('queue_update', getQueue);  // Added every time
}

// ✅ GOOD - Clean up before adding
function loadQueueView() {
  socket.off('queue_update');  // Remove old
  socket.on('queue_update', getQueue);  // Add new
}
```

### 10.3 Namespace Handlers by View
```javascript
// ✅ GOOD - Track which handlers belong to which view
const viewHandlers = {
  queue: {
    'queue_update': getQueue
  },
  home: {
    'now_playing': handleNowPlaying
  }
};

function cleanupView(viewName) {
  Object.entries(viewHandlers[viewName] || {}).forEach(([event, handler]) => {
    socket.off(event, handler);
  });
}
```

### 10.4 Global vs View-Specific Events
```javascript
// Global events (never cleaned up)
socket.on('notification', showNotification);  // All views need this

// View-specific events (cleaned up on view change)
function initQueueView() {
  socket.on('queue_update', getQueue);  // Only queue view needs this
}
```

---

## 11. Files to Modify

### Option B (Hybrid - Recommended)

**Modified:**
- `pikaraoke/templates/splash.html` - Replace iframe with DIV, add loadMenuContent()
- `pikaraoke/routes/menu.py` - NEW file for content-only endpoints
- `pikaraoke/app.py` - Register menu blueprint

**Total: 2 modified, 1 new file**

### Option A (Full SPA)

**Modified:**
- `pikaraoke/templates/base.html` → `index.html` (restructure)
- `pikaraoke/templates/home.html` → `home_content.html`
- `pikaraoke/templates/queue.html` → `queue_content.html`
- `pikaraoke/templates/search.html` → `search_content.html`
- `pikaraoke/templates/files.html` → `files_content.html`
- `pikaraoke/templates/info.html` → `info_content.html`
- `pikaraoke/templates/splash.html` - Remove iframe, use router

**New:**
- `pikaraoke/static/router.js` - Client-side router
- `pikaraoke/static/socket-manager.js` - Socket singleton
- `pikaraoke/routes/api.py` - Content-only endpoints

**Total: 7 modified, 3 new files**

---

## 12. Testing Strategy

### Unit Tests
- Socket manager singleton behavior
- Router path matching
- Event handler cleanup
- HTML parsing and injection

### Integration Tests
- Navigate between all pages
- Socket events fire correctly on each page
- No duplicate event handlers
- Browser back/forward navigation
- Direct URL access
- Refresh behavior

### Performance Tests
- Page load time comparison (iframe vs DIV)
- Memory usage after 100 navigation cycles
- Socket reconnection speed
- Concurrent users (Socket.IO scalability)

### Browser Compatibility
- Chrome (desktop + mobile)
- Safari (desktop + mobile)
- Firefox
- Edge
- Samsung Internet (if mobile is important)

---

## 13. Rollback Plan

### Option B (Low Risk)
1. Git revert the splash.html changes
2. Remove menu.py route
3. Restart Flask app
4. Iframe is back

### Option A (Higher Risk)
1. Feature flag to toggle SPA on/off
2. Keep old templates in `templates/legacy/`
3. Route `/legacy/home` to old templates
4. If issues detected, flip feature flag
5. Full rollback requires redeployment

---

## 14. Conclusion

**Recommended Approach: Option B (Hybrid SPA)**

This approach:
- ✅ Solves the iframe performance/UX issues
- ✅ Minimal code changes (low risk)
- ✅ Can be implemented quickly (0.5-1 day)
- ✅ Doesn't require Socket.IO refactoring
- ✅ Keeps jQuery (no library migration needed)
- ✅ Easy to test and rollback
- ✅ Provides foundation for future full SPA migration

**Next Steps:**
1. Review this analysis
2. Confirm Option B is the desired approach
3. Create implementation task list
4. Implement changes
5. Test thoroughly
6. Deploy to staging
7. User acceptance testing
8. Deploy to production
9. Monitor for issues

**Long-term Roadmap:**
1. Phase 1: Option B (Hybrid) - **Now**
2. Phase 2: Add comprehensive tests - **Next 2-3 months**
3. Phase 3: Evaluate user feedback on hybrid approach - **After 3 months**
4. Phase 4: Consider full SPA (Option A) - **6+ months, if needed**
5. Phase 5: Consider jQuery → Vanilla JS - **12+ months, if needed**

---

## Appendix A: Code Snippets for Option B Implementation

### A.1 Updated splash.html (lines 492-511)

```javascript
var showMenu = false;

// Load menu content dynamically
function loadMenuContent(page = '/') {
  $.get(page, function(html) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');

    // Extract content box (skip navbar to avoid duplication)
    const contentBox = doc.querySelector('.box');

    if (contentBox) {
      $('#menu-content').html(contentBox.innerHTML);

      // Get page-specific scripts
      const scripts = doc.querySelectorAll('script');
      scripts.forEach(script => {
        if (script.innerHTML && !script.src) {
          // Execute inline scripts
          try {
            eval(script.innerHTML);
          } catch (e) {
            console.error('Error executing script:', e);
          }
        }
      });

      // Attach navigation handlers
      $('#menu-content a.navbar-item').on('click', function(e) {
        const href = $(this).attr('href');
        // Only intercept internal links
        if (href && !href.startsWith('http') && !href.startsWith('#')) {
          e.preventDefault();
          loadMenuContent(href);
        }
      });

      // Re-initialize any page-specific functionality
      if (typeof loadNowPlaying === 'function') {
        loadNowPlaying();
      }
      if (typeof getQueue === 'function') {
        getQueue();
      }
    }
  }).fail(function(error) {
    console.error('Failed to load menu content:', error);
    $('#menu-content').html('<div class="notification is-danger">Failed to load page</div>');
  });
}

// Menu toggle
$('#menu a').click(function () {
  if (showMenu) {
    $('#menu-container').hide();
    $('#menu-content').html('');
    showMenu = false;
  } else {
    setUserCookie();
    $("#menu-container").show();
    loadMenuContent('/');
    showMenu = true;
  }
});

// Close menu clicking outside
$('#menu-background').click(function () {
  if (showMenu) {
    $(".navbar-burger").click();
  }
});
```

### A.2 Updated splash.html HTML (lines 762-765)

```html
<div id="menu-background" class="overlay"></div>
<div id="menu-container" class="">
  <div id="menu-content"></div>
</div>
```

### A.3 Updated splash.html CSS (lines 907-920)

```css
#menu-container {
  position: absolute;
  z-index: 3;
  top: 40px;
  left: 20px;
  display: none;
  overflow: hidden;
}

#menu-content {
  width: 600px;
  height: 75vh;
  overflow-y: auto;
  overflow-x: hidden;
  background-color: #363636;
  padding: 0;
  border-radius: 6px;
  box-shadow: 0 0.5em 1em -0.125em rgba(10, 10, 10, 0.1);
}

/* Ensure scrollbar is visible */
#menu-content::-webkit-scrollbar {
  width: 8px;
}

#menu-content::-webkit-scrollbar-track {
  background: #2b2b2b;
}

#menu-content::-webkit-scrollbar-thumb {
  background: #4a4a4a;
  border-radius: 4px;
}

#menu-content::-webkit-scrollbar-thumb:hover {
  background: #5a5a5a;
}
```

---

## Appendix B: Alternative Fetch API Implementation

If you decide to use Fetch API instead of jQuery for menu loading:

```javascript
async function loadMenuContent(page = '/') {
  try {
    const response = await fetch(page);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const html = await response.text();
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');

    const contentBox = doc.querySelector('.box');

    if (contentBox) {
      document.getElementById('menu-content').innerHTML = contentBox.innerHTML;

      // Execute scripts
      const scripts = doc.querySelectorAll('script');
      scripts.forEach(script => {
        if (script.innerHTML && !script.src) {
          try {
            eval(script.innerHTML);
          } catch (e) {
            console.error('Error executing script:', e);
          }
        }
      });

      // Attach navigation handlers (vanilla JS)
      document.querySelectorAll('#menu-content a.navbar-item').forEach(link => {
        const href = link.getAttribute('href');
        if (href && !href.startsWith('http') && !href.startsWith('#')) {
          link.addEventListener('click', (e) => {
            e.preventDefault();
            loadMenuContent(href);
          });
        }
      });

      // Re-initialize
      if (typeof loadNowPlaying === 'function') {
        loadNowPlaying();
      }
      if (typeof getQueue === 'function') {
        getQueue();
      }
    }
  } catch (error) {
    console.error('Failed to load menu content:', error);
    document.getElementById('menu-content').innerHTML =
      '<div class="notification is-danger">Failed to load page</div>';
  }
}
```

---

**End of Analysis**
