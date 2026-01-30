
import random

def get_randomized_screen():
    """Generate randomized but realistic screen dimensions"""
    width = random.randint(1366, 1920)
    height = random.randint(768, 1080)
    return {"width": width, "height": height}

STEALTH_SCRIPT = """
(() => {
    // 1. Mask WebDriver (The most important check)
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // 2. Mock Chrome Object (Crucial for passing basic bot checks)
    if (!window.chrome) {
        window.chrome = {
            runtime: {},
            app: {
                isInstalled: false,
                InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
            },
            csi: () => {},
            loadTimes: () => {}
        };
    }

    // 3. Mask Permissions (Force 'denied' for notifications to look natural)
    if (navigator.permissions) {
        const originalQuery = navigator.permissions.query;
        navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
            Promise.resolve({ state: 'denied', onchange: null }) :
            originalQuery(parameters)
        );
    }

    // 4. Mock Plugins (Empty array signals headless, we populate it)
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            var plugin1 = { name: "Chrome PDF Plugin", filename: "internal-pdf-viewer", description: "Portable Document Format" };
            var plugin2 = { name: "Chrome PDF Viewer", filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai", description: "Portable Document Format" };
            var plugin3 = { name: "Native Client", filename: "internal-nacl-plugin", description: "" };
            return [plugin1, plugin2, plugin3];
        }
    });

    // 5. Mask Languages
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

    // 6. Mask WebGL (Hide Linux/Headless GPU signatures)
    try {
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            // Vendor: Google Inc. (Intel) -> Looks like a standard laptop
            if (parameter === 37445) return 'Google Inc. (Intel)';
            // Renderer: ANGLE (Intel, Intel(R) Iris(TM) Plus Graphics 640, or similar)
            if (parameter === 37446) return 'ANGLE (Intel, Intel(R) Iris(TM) Plus Graphics 640, OpenGL 4.1)';
            return getParameter.apply(this, arguments);
        };
    } catch (e) {}

    // 7. Randomize Hardware Concurrency
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });

    // 8. Mask Device Memory
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

    // 9. Hide Automation Features
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
    
    // 10. Override Permission API for more realism
    Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
})();
"""
