// Zotero bootstrapped plugin entry point (Zotero 7-10).
/* global Zotero, Services */

var PLUGIN_DATA = null; // { id, version, rootURI }
var PaperLoomPlugin = null;
var PluginWindow = null;

function log(message) {
  try {
    Zotero.debug("PaperLoom: " + message);
  } catch (_error) {
    // Zotero may not be available during uninstall.
  }
}

function install() {
  log("installed");
}

function uninstall() {
  log("uninstalled");
}

function mainWindow() {
  try {
    const windows = Zotero.getMainWindows();
    return windows && windows.length ? windows[0] : null;
  } catch (_error) {
    return null;
  }
}

/**
 * The bundle is loaded into a real chrome window (not the bootstrap scope) so
 * that React sees a real `window`/`document` and can mount into reader iframes.
 */
function loadBundle(win, rootURI) {
  if (!win || !win.document) {
    return null;
  }
  if (win.PaperLoom && win.PaperLoom.__paperloomApi) {
    return win.PaperLoom;
  }
  Services.scriptloader.loadSubScript(rootURI + "content/plugin.js", win);
  return win.PaperLoom || null;
}

async function startInWindow(win) {
  if (!PLUGIN_DATA) {
    return;
  }
  if (PluginWindow === win && PaperLoomPlugin) {
    return;
  }
  const api = loadBundle(win, PLUGIN_DATA.rootURI);
  if (!api) {
    log("bundle did not expose the PaperLoom API");
    return;
  }
  PaperLoomPlugin = api;
  PluginWindow = win;
  await api.startup(PLUGIN_DATA);
  log("started " + PLUGIN_DATA.version);
}

async function startup({ id, version, rootURI }, reason) {
  PLUGIN_DATA = { id, version, rootURI };
  log("startup " + version + " (reason " + reason + ")");
  try {
    await Zotero.initializationPromise;
  } catch (_error) {
    // startup is called after initialization anyway.
  }
  const win = mainWindow();
  if (!win) {
    log("no main window yet; will start on onMainWindowLoad");
    return;
  }
  try {
    await startInWindow(win);
  } catch (error) {
    log("startup failed: " + (error && error.stack ? error.stack : error));
  }
}

function shutdown(data, reason) {
  if (typeof APP_SHUTDOWN !== "undefined" && reason === APP_SHUTDOWN) {
    return;
  }
  log("shutdown (reason " + reason + ")");
  try {
    if (PaperLoomPlugin) {
      PaperLoomPlugin.shutdown();
    }
  } catch (error) {
    log("shutdown failed: " + error);
  }
  PaperLoomPlugin = null;
  PluginWindow = null;
  PLUGIN_DATA = null;
}

function onMainWindowLoad({ window }) {
  try {
    if (!PaperLoomPlugin) {
      void startInWindow(window);
      return;
    }
    PaperLoomPlugin.onWindowLoad(window);
  } catch (error) {
    log("onMainWindowLoad failed: " + error);
  }
}

function onMainWindowUnload({ window }) {
  try {
    if (PaperLoomPlugin) {
      PaperLoomPlugin.onWindowUnload(window);
    }
  } catch (error) {
    log("onMainWindowUnload failed: " + error);
  }
  if (window === PluginWindow) {
    PaperLoomPlugin = null;
    PluginWindow = null;
  }
}
