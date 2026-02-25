import random
import hashlib
from typing import Dict, Tuple
from datetime import datetime

BROWSER_PROFILES = [
    {
        "name": "Chrome 128 Windows",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "platform": "Win32",
        "viewport": {"width": 1920, "height": 1080},
        "device_memory": 8,
        "hardware_concurrency": 8,
        "webgl_vendor": "Google Inc. (Intel)",
        "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630, OpenGL 4.5)",
        "max_touch_points": 0
    },
    {
        "name": "Chrome 127 Windows",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "platform": "Win32",
        "viewport": {"width": 1680, "height": 1050},
        "device_memory": 8,
        "hardware_concurrency": 12,
        "webgl_vendor": "Google Inc. (NVIDIA)",
        "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650, OpenGL 4.5)",
        "max_touch_points": 0
    },
    {
        "name": "Edge 128 Windows",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
        "platform": "Win32",
        "viewport": {"width": 1536, "height": 864},
        "device_memory": 16,
        "hardware_concurrency": 16,
        "webgl_vendor": "Google Inc. (AMD)",
        "webgl_renderer": "ANGLE (AMD, AMD Radeon RX 580, OpenGL 4.5)",
        "max_touch_points": 0
    }
]

def get_fingerprint(seed: str = None) -> Dict:
    if seed:
        random.seed(hashlib.md5(seed.encode()).hexdigest())
    
    profile = random.choice(BROWSER_PROFILES)
    
    return {
        "user_agent": profile["user_agent"],
        "platform": profile["platform"],
        "viewport": profile["viewport"].copy(),
        "device_memory": profile["device_memory"],
        "hardware_concurrency": profile["hardware_concurrency"],
        "webgl_vendor": profile["webgl_vendor"],
        "webgl_renderer": profile["webgl_renderer"],
        "max_touch_points": profile["max_touch_points"]
    }

def get_stealth_script(fingerprint: Dict) -> str:
    vendor = fingerprint.get("webgl_vendor", "Google Inc. (Intel)")
    renderer = fingerprint.get("webgl_renderer", "ANGLE (Intel)")
    platform = fingerprint.get("platform", "Win32")
    concurrency = fingerprint.get("hardware_concurrency", 8)
    memory = fingerprint.get("device_memory", 8)
    max_touch = fingerprint.get("max_touch_points", 0)
    
    viewport = fingerprint.get('viewport', {})
    screen_width = viewport.get('width', 1920)
    screen_height = viewport.get('height', 1080)
    
    return f"""
(function() {{
    'use strict';
    
    const objectToString = Object.prototype.toString;
    const functionToString = Function.prototype.toString;
    
    const makeNativeFunction = (func) => {{
        const proxy = new Proxy(func, {{
            apply(target, thisArg, args) {{
                return Reflect.apply(target, thisArg, args);
            }},
            get(target, prop) {{
                if (prop === 'toString') {{
                    return () => 'function ' + target.name + '() {{ [native code] }}';
                }}
                return Reflect.get(target, prop);
            }}
        }});
        return proxy;
    }};
    
    try {{
        Object.defineProperty(navigator, 'webdriver', {{
            get: () => undefined,
            enumerable: true,
            configurable: true
        }});
    }} catch(e) {{}}
    
    try {{
        delete navigator.__proto__.webdriver;
    }} catch(e) {{}}
    
    try {{
        Object.defineProperty(Navigator.prototype, 'webdriver', {{
            get: () => undefined,
            enumerable: true,
            configurable: true
        }});
    }} catch(e) {{}}
    
    try {{
        const originalNavigator = navigator;
        const navigatorProxy = new Proxy(originalNavigator, {{
            get(target, prop) {{
                if (prop === 'webdriver') {{
                    return undefined;
                }}
                return Reflect.get(target, prop);
            }}
        }});
    }} catch(e) {{}}
    
    try {{
        Object.defineProperty(navigator, 'platform', {{
            get: () => '{platform}',
            enumerable: true,
            configurable: true
        }});
    }} catch(e) {{}}
    
    try {{
        Object.defineProperty(navigator, 'hardwareConcurrency', {{
            get: () => {concurrency},
            enumerable: true,
            configurable: true
        }});
    }} catch(e) {{}}
    
    try {{
        Object.defineProperty(navigator, 'deviceMemory', {{
            get: () => {memory},
            enumerable: true,
            configurable: true
        }});
    }} catch(e) {{}}
    
    try {{
        Object.defineProperty(navigator, 'maxTouchPoints', {{
            get: () => {max_touch},
            enumerable: true,
            configurable: true
        }});
    }} catch(e) {{}}
    
    try {{
        Object.defineProperty(navigator, 'languages', {{
            get: () => ['en-US', 'en'],
            enumerable: true,
            configurable: true
        }});
    }} catch(e) {{}}
    
    try {{
        if (!window.chrome) {{
            window.chrome = {{}};
        }}
        
        window.chrome.runtime = {{
            connect: makeNativeFunction(() => ({{}})),
            sendMessage: makeNativeFunction(() => ({{}}))
        }};
        
        window.chrome.app = {{
            isInstalled: false,
            InstallState: {{
                DISABLED: 'disabled',
                INSTALLED: 'installed',
                NOT_INSTALLED: 'not_installed'
            }},
            RunningState: {{
                CANNOT_RUN: 'cannot_run',
                READY_TO_RUN: 'ready_to_run',
                RUNNING: 'running'
            }}
        }};
        
        window.chrome.csi = makeNativeFunction(function() {{ return {{}}; }});
        window.chrome.loadTimes = makeNativeFunction(function() {{ return {{}}; }});
    }} catch(e) {{}}
    
    try {{
        if (navigator.permissions) {{
            const originalQuery = navigator.permissions.query;
            navigator.permissions.query = makeNativeFunction((parameters) => {{
                if (parameters.name === 'notifications') {{
                    return Promise.resolve({{
                        state: 'denied',
                        status: 'denied',
                        onchange: null
                    }});
                }}
                return originalQuery.call(navigator.permissions, parameters);
            }});
        }}
    }} catch(e) {{}}
    
    try {{
        const createPluginArray = () => {{
            const plugins = [
                {{
                    name: 'PDF Viewer',
                    filename: 'internal-pdf-viewer',
                    description: 'Portable Document Format',
                    length: 2
                }},
                {{
                    name: 'Chrome PDF Viewer',
                    filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                    description: 'Portable Document Format',
                    length: 2
                }},
                {{
                    name: 'Chromium PDF Viewer',
                    filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                    description: 'Portable Document Format',
                    length: 2
                }},
                {{
                    name: 'Microsoft Edge PDF Viewer',
                    filename: 'pdf',
                    description: 'Portable Document Format',
                    length: 2
                }},
                {{
                    name: 'WebKit built-in PDF',
                    filename: 'pdf',
                    description: 'Portable Document Format',
                    length: 2
                }}
            ];
            
            Object.setPrototypeOf(plugins, PluginArray.prototype);
            plugins.item = makeNativeFunction(function(index) {{ return this[index] || null; }});
            plugins.namedItem = makeNativeFunction(function(name) {{ 
                return this.find(p => p.name === name) || null; 
            }});
            plugins.refresh = makeNativeFunction(function() {{}});
            
            return plugins;
        }};
        
        Object.defineProperty(navigator, 'plugins', {{
            get: () => createPluginArray(),
            enumerable: true,
            configurable: true
        }});
    }} catch(e) {{}}
    
    try {{
        const getParameterProxyHandler = {{
            apply(target, thisArg, args) {{
                const param = args[0];
                if (param === 37445) return '{vendor}';
                if (param === 37446) return '{renderer}';
                return Reflect.apply(target, thisArg, args);
            }}
        }};
        
        const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = new Proxy(
            originalGetParameter,
            getParameterProxyHandler
        );
        
        const originalGetParameter2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = new Proxy(
            originalGetParameter2,
            getParameterProxyHandler
        );
    }} catch(e) {{}}
    
    try {{
        const toStringProxy = new Proxy(Function.prototype.toString, {{
            apply(target, thisArg, args) {{
                if (thisArg === navigator.permissions.query) {{
                    return 'function query() {{ [native code] }}';
                }}
                return Reflect.apply(target, thisArg, args);
            }}
        }});
        
        Function.prototype.toString = toStringProxy;
    }} catch(e) {{}}
    
    const automationProps = [
        'webdriver',
        'cdc_adoQpoasnfa76pfcZLmcfl_Array',
        'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
        'cdc_adoQpoasnfa76pfcZLmcfl_Symbol',
        '$cdc_asdjflasutopfhvcZLmcfl_',
        '$chrome_asyncScriptInfo',
        '__webdriver_script_fn',
        '__driver_evaluate',
        '__webdriver_evaluate',
        '__selenium_evaluate',
        '__fxdriver_evaluate',
        '__driver_unwrapped',
        '__webdriver_unwrapped',
        '__selenium_unwrapped',
        '__fxdriver_unwrapped',
        '__webdriver_script_func',
        '__webdriver_script_function',
        'calledSelenium',
        '_Selenium_IDE_Recorder',
        '_selenium',
        'callSelenium',
        '__nightmare',
        '_phantom',
        'phantom',
        'callPhantom',
        '__phantomas',
        'domAutomation',
        'domAutomationController'
    ];
    
    automationProps.forEach(prop => {{
        try {{
            delete window[prop];
            delete window.document[prop];
            delete window.navigator[prop];
        }} catch(e) {{}}
        
        try {{
            Object.defineProperty(window, prop, {{
                get: () => undefined,
                set: () => {{}},
                configurable: true,
                enumerable: false
            }});
        }} catch(e) {{}}
    }});
    
    try {{
        const screenProps = {{
            width: {screen_width},
            height: {screen_height},
            availWidth: {screen_width},
            availHeight: {screen_height - 40},
            colorDepth: 24,
            pixelDepth: 24
        }};
        
        Object.keys(screenProps).forEach(prop => {{
            Object.defineProperty(screen, prop, {{
                get: () => screenProps[prop],
                enumerable: true,
                configurable: true
            }});
        }});
    }} catch(e) {{}}
    
    try {{
        Object.defineProperty(navigator.connection || {{}}, 'rtt', {{
            get: () => Math.floor(Math.random() * 100) + 50,
            enumerable: true,
            configurable: true
        }});
    }} catch(e) {{}}
}})();
"""

STEALTH_SCRIPT = get_stealth_script(get_fingerprint())