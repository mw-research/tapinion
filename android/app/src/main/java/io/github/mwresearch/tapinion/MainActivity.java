// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
package io.github.mwresearch.tapinion;

import android.annotation.SuppressLint;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.net.Uri;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.net.wifi.WifiManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.LayoutInflater;
import android.view.View;
import android.view.WindowManager;
import android.view.inputmethod.EditorInfo;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

import com.google.android.material.switchmaterial.SwitchMaterial;
import com.journeyapps.barcodescanner.ScanContract;
import com.journeyapps.barcodescanner.ScanOptions;

import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Tapinion for Android – the slim companion of the program on the computer:
 * - connects to Tapinion (found in the Wi-Fi by itself, or by QR code) and shows its kiosk;
 * - keeps every event opened here for offline use and runs the kiosk without the computer;
 * - sends the ratings collected offline once the computer is reachable again (also at a new
 *   address: it is found again in the Wi-Fi by its installation id);
 * - shows the results of its offline events. Events are created on the computer only.
 */
public class MainActivity extends AppCompatActivity {
    private static final String PREFS = "tapinion";
    private static final String KEY_URL = "url";
    private static final String KEY_INSTANCE = "instance";
    private static final String KEY_PIN_APP = "pin_app";
    private static final String KEY_LAST_KIOSK = "last_kiosk";          // web kiosk that was running
    private static final String KEY_RUNNING_OFFLINE = "running_offline"; // offline kiosk that was running
    private static final String KEY_ACTIVE_KIOSK = "active_kiosk";      // token of a kiosk that is unlocked; left with the PIN only
    private static final String SERVICE_TYPE = "_tapinion._tcp";
    private static final long SYNC_EVERY_MS = 60_000;

    private enum Mode { SETUP, CONNECTING, WEB, OFFLINE_KIOSK, RESULTS }
    private static final long PAGE_TIMEOUT_MS = 12_000;  // a page that takes longer counts as unreachable

    private SharedPreferences prefs;
    private OfflineStore store;
    private final ExecutorService background = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private Mode mode = Mode.SETUP;
    private WebView web;
    private String origin;
    private boolean pinned;
    private volatile boolean syncing;
    private int attempt;             // connection attempts; a cancelled one is ignored when it finishes
    private int webFailures;         // consecutive failed page loads
    private boolean pageFinished;
    private boolean kioskRunning;    // the web kiosk is unlocked and running (reported by the page)
    private boolean offlineStarted;  // the offline kiosk is past its PIN screen
    private final Runnable pageWatchdog = () -> {
        if (mode == Mode.WEB && !pageFinished && web != null) {
            String u = web.getUrl() == null ? prefs.getString(KEY_URL, "") : web.getUrl();
            web.stopLoading();
            unreachable(u);
        }
    };

    // start screen
    private LinearLayout foundList, offlineList;
    private View searching, offlineSection;
    private TextView syncStatus;

    // network discovery for the start screen
    private NsdManager nsd;
    private NsdManager.DiscoveryListener discovery;
    private WifiManager.MulticastLock multicastLock;
    private final ArrayDeque<NsdServiceInfo> toResolve = new ArrayDeque<>();
    private boolean resolving;
    private final Set<String> shown = new HashSet<>();

    private final ActivityResultLauncher<ScanOptions> scanner = registerForActivityResult(new ScanContract(), result -> {
        if (result.getContents() != null) connect(result.getContents().trim());
    });

    private final Runnable syncTick = new Runnable() {
        @Override
        public void run() {
            runSync(false);
            main.postDelayed(this, SYNC_EVERY_MS);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        store = new OfflineStore(this);
        nsd = (NsdManager) getSystemService(Context.NSD_SERVICE);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                onBack();
            }
        });
        route();
    }

    /** Where to continue after a start: a running offline kiosk, a running web kiosk, or the start screen. */
    private void route() {
        String running = prefs.getString(KEY_RUNNING_OFFLINE, null);
        String url = prefs.getString(KEY_URL, null);
        String kiosk = prefs.getString(KEY_LAST_KIOSK, null);
        if (running != null && store.has(running)) {
            showOfflineKiosk(running, false);
        } else if (url == null) {
            showSetup(null);
        } else {
            showConnecting(kiosk != null ? kiosk : url);
        }
    }

    /**
     * Check that the computer answers before loading anything: at most a few seconds, then the
     * kiosk (computer reachable, also at a new address), the offline kiosk, or the start screen.
     * Can be cancelled at any time.
     */
    private void showConnecting(String target) {
        if (prefs.getString(KEY_ACTIVE_KIOSK, null) != null) startPinning();  // a running kiosk stays locked
        else stopPinning();
        stopDiscovery();
        main.removeCallbacks(pageWatchdog);
        mode = Mode.CONNECTING;
        web = null;
        foundList = offlineList = null;
        setContentView(R.layout.activity_connecting);
        showSystemBars(true);
        String o = originOf(target);
        ((TextView) findViewById(R.id.connecting_address)).setText(o.replace("http://", ""));
        int my = ++attempt;
        TextView cancel = findViewById(R.id.connecting_cancel);
        if (guardedToken() != null) cancel.setText(R.string.connecting_continue_offline);
        cancel.setOnClickListener(v -> cancelConnecting());
        String instance = prefs.getString(KEY_INSTANCE, null);
        new Thread(() -> {
            String found = OfflineStore.instanceAt(o) != null ? o : null;
            if (found == null && instance != null) found = Rediscover.find(this, instance, 5_000);
            String result = found;
            runOnUiThread(() -> {
                if (my != attempt || mode != Mode.CONNECTING) return;  // cancelled meanwhile
                if (result != null) {
                    if (!result.equals(o)) movedTo(instance, o, result);
                    showWeb(result + target.substring(o.length()));
                } else {
                    continueOffline(target);
                }
            });
        }, "tapinion-connect").start();
    }

    /** A kiosk is unlocked and running (also seen from the boot receiver). */
    static boolean kioskActive(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_ACTIVE_KIOSK, null) != null;
    }

    /** The token of a running kiosk that is stored on the device, else null. */
    private String guardedToken() {
        String token = prefs.getString(KEY_ACTIVE_KIOSK, null);
        return token != null && store.has(token) ? token : null;
    }

    /** Leave the connecting screen: a running kiosk continues offline (PIN to leave), else the overview. */
    private void cancelConnecting() {
        attempt++;
        String token = guardedToken();
        if (token != null) {
            showOfflineKiosk(token, false);
        } else {
            prefs.edit().remove(KEY_ACTIVE_KIOSK).apply();  // nothing to protect on this device
            showSetup(null);
        }
    }

    /** Computer not reachable: continue a running kiosk from the device, else the start screen. */
    private void continueOffline(String failedUrl) {
        String token = tokenOf(prefs.getString(KEY_LAST_KIOSK, null));
        if (token == null) token = tokenOf(failedUrl);
        if (token != null && store.has(token)) {
            showOfflineKiosk(token, false);
        } else {
            showSetup(getString(R.string.unreachable, originOf(failedUrl).replace("http://", "")));
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        main.removeCallbacks(syncTick);
        main.postDelayed(syncTick, 5_000);
        if (mode == Mode.SETUP) startDiscovery();
    }

    @Override
    protected void onPause() {
        super.onPause();
        main.removeCallbacks(syncTick);
        stopDiscovery();
    }

    // --- start screen ---------------------------------------------------------

    private void showSetup(String error) {
        prefs.edit().remove(KEY_ACTIVE_KIOSK).apply();  // the overview is only reached once no kiosk runs
        stopPinning();
        main.removeCallbacks(pageWatchdog);
        mode = Mode.SETUP;
        web = null;
        setContentView(R.layout.activity_setup);
        showSystemBars(true);

        findViewById(R.id.scan).setOnClickListener(v -> scan());
        View manual = findViewById(R.id.manual);
        EditText address = findViewById(R.id.address);
        String current = prefs.getString(KEY_URL, null);
        if (current != null) address.setText(current);
        findViewById(R.id.manual_toggle).setOnClickListener(v -> {
            manual.setVisibility(manual.getVisibility() == View.VISIBLE ? View.GONE : View.VISIBLE);
            if (manual.getVisibility() == View.VISIBLE) address.requestFocus();
        });
        findViewById(R.id.connect).setOnClickListener(v -> connect(address.getText().toString().trim()));
        address.setOnEditorActionListener((v, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_GO) {
                connect(address.getText().toString().trim());
                return true;
            }
            return false;
        });
        SwitchMaterial pin = findViewById(R.id.pin_app);
        pin.setChecked(prefs.getBoolean(KEY_PIN_APP, true));
        pin.setOnCheckedChangeListener((b, checked) -> prefs.edit().putBoolean(KEY_PIN_APP, checked).apply());
        renderLock(pin);
        TextView err = findViewById(R.id.error);
        if (error != null) {
            err.setText(error);
            err.setVisibility(View.VISIBLE);
        }

        offlineSection = findViewById(R.id.offline_section);
        offlineList = findViewById(R.id.offline_list);
        syncStatus = findViewById(R.id.sync_status);
        findViewById(R.id.sync).setOnClickListener(v -> runSync(true));
        renderOffline();
        if (!store.list().isEmpty()) runSync(false);

        foundList = findViewById(R.id.found_list);
        searching = findViewById(R.id.searching);
        shown.clear();
        startDiscovery();
    }

    private void renderOffline() {
        if (offlineList == null || mode != Mode.SETUP) return;
        List<OfflineStore.Entry> entries = store.list();
        offlineSection.setVisibility(entries.isEmpty() ? View.GONE : View.VISIBLE);
        offlineList.removeAllViews();
        for (OfflineStore.Entry e : entries) {
            View card = LayoutInflater.from(this).inflate(R.layout.item_offline, offlineList, false);
            ((TextView) card.findViewById(R.id.off_name)).setText(e.name);
            String status;
            if (e.switchedOff) status = getString(R.string.offline_status_off, e.date);
            else if (e.pending > 0) status = getString(R.string.offline_status_pending, e.date, e.pending);
            else if (!e.active) status = getString(R.string.offline_status_closed, e.date);
            else status = getString(R.string.offline_status_synced, e.date);
            ((TextView) card.findViewById(R.id.off_status)).setText(status);
            View start = card.findViewById(R.id.off_start);
            start.setEnabled(!e.switchedOff);
            start.setOnClickListener(v -> showOfflineKiosk(e.token, true));
            card.findViewById(R.id.off_results).setOnClickListener(v -> showResults(e.token));
            card.findViewById(R.id.off_delete).setOnClickListener(v -> confirmDelete(e));
            offlineList.addView(card);
        }
    }

    private void confirmDelete(OfflineStore.Entry e) {
        AlertDialog.Builder dlg = new AlertDialog.Builder(this).setTitle(getString(R.string.offline_delete_question, e.name));
        if (e.pending > 0) dlg.setMessage(getString(R.string.offline_delete_pending, e.pending));
        dlg.setPositiveButton(R.string.offline_delete, (d, w) -> {
            store.remove(e.token);
            if (e.token.equals(prefs.getString(KEY_RUNNING_OFFLINE, null))) prefs.edit().remove(KEY_RUNNING_OFFLINE).apply();
            renderOffline();
        }).setNegativeButton(android.R.string.cancel, null).show();
    }

    private void scan() {
        ScanOptions options = new ScanOptions();
        options.setDesiredBarcodeFormats(ScanOptions.QR_CODE);
        options.setPrompt(getString(R.string.setup_scan_prompt));
        options.setBeepEnabled(false);
        options.setOrientationLocked(false);
        scanner.launch(options);
    }

    private void connect(String raw) {
        if (raw.isEmpty()) return;
        if (!raw.startsWith("http://") && !raw.startsWith("https://")) raw = "http://" + raw;
        Uri uri = Uri.parse(raw);
        if (uri.getHost() == null) {
            showSetup(getString(R.string.setup_invalid));
            return;
        }
        stopDiscovery();
        prefs.edit().putString(KEY_URL, raw).remove(KEY_LAST_KIOSK).remove(KEY_INSTANCE).apply();
        String base = uri.getScheme() + "://" + uri.getAuthority();
        background.execute(() -> {
            String instance = OfflineStore.instanceAt(base);
            if (instance != null && !instance.isEmpty()) prefs.edit().putString(KEY_INSTANCE, instance).apply();
        });
        showConnecting(raw);
    }

    // --- synchronisation --------------------------------------------------------

    /** Find moved computers again, send waiting ratings, refresh offline events. */
    private void runSync(boolean showStatus) {
        if (syncing) return;
        syncing = true;
        if (showStatus && syncStatus != null) {
            syncStatus.setText(R.string.sync_running);
            syncStatus.setVisibility(View.VISIBLE);
        }
        background.execute(() -> {
            OfflineStore.SyncResult r;
            try {
                rediscoverAll();
                r = store.syncAll();
            } finally {
                syncing = false;
            }
            OfflineStore.SyncResult result = r;
            runOnUiThread(() -> {
                if (mode != Mode.SETUP) return;
                renderOffline();
                if (showStatus && syncStatus != null) {
                    syncStatus.setText(result.reachable ? getString(R.string.sync_done, result.sent)
                            : getString(R.string.sync_unreachable));
                }
            });
        });
    }

    /** Computers whose address changed are looked up in the Wi-Fi by their installation id. */
    private void rediscoverAll() {
        Map<String, String> instances = new HashMap<>();  // instance -> known origin
        for (OfflineStore.Entry e : store.list()) {
            if (!e.instance.isEmpty()) instances.put(e.instance, e.origin);
        }
        String url = prefs.getString(KEY_URL, null);
        String myInstance = prefs.getString(KEY_INSTANCE, null);
        if (url != null && myInstance != null) instances.put(myInstance, originOf(url));
        for (Map.Entry<String, String> it : instances.entrySet()) {
            if (OfflineStore.instanceAt(it.getValue()) != null) continue;
            String moved = Rediscover.find(this, it.getKey(), 6_000);
            if (moved != null) movedTo(it.getKey(), it.getValue(), moved);
        }
    }

    private void movedTo(String instance, String oldOrigin, String newOrigin) {
        store.moveOrigin(instance, newOrigin);
        if (instance.equals(prefs.getString(KEY_INSTANCE, null))) {
            SharedPreferences.Editor ed = prefs.edit();
            for (String key : new String[]{KEY_URL, KEY_LAST_KIOSK}) {
                String u = prefs.getString(key, null);
                if (u != null && u.startsWith(oldOrigin)) ed.putString(key, newOrigin + u.substring(oldOrigin.length()));
            }
            ed.apply();
        }
    }

    private static String originOf(String url) {
        Uri u = Uri.parse(url);
        return u.getScheme() + "://" + u.getAuthority();
    }

    // --- finding Tapinion in the Wi-Fi for the start screen ---------------------

    private void startDiscovery() {
        if (discovery != null || nsd == null || foundList == null) return;
        try {
            WifiManager wifi = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            if (wifi != null) {
                multicastLock = wifi.createMulticastLock("tapinion");
                multicastLock.setReferenceCounted(false);
                multicastLock.acquire();
            }
        } catch (Exception ignored) {
        }
        discovery = new NsdManager.DiscoveryListener() {
            @Override public void onDiscoveryStarted(String type) { }
            @Override public void onDiscoveryStopped(String type) { }
            @Override public void onStartDiscoveryFailed(String type, int code) { discovery = null; }
            @Override public void onStopDiscoveryFailed(String type, int code) { }
            @Override public void onServiceLost(NsdServiceInfo info) { }

            @Override
            public void onServiceFound(NsdServiceInfo info) {
                runOnUiThread(() -> {
                    toResolve.add(info);
                    resolveNext();
                });
            }
        };
        try {
            nsd.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, discovery);
        } catch (Exception e) {
            discovery = null;
        }
    }

    private void resolveNext() {
        if (resolving || toResolve.isEmpty() || discovery == null) return;
        resolving = true;
        NsdServiceInfo next = toResolve.poll();
        nsd.resolveService(next, new NsdManager.ResolveListener() {
            @Override
            public void onResolveFailed(NsdServiceInfo info, int code) {
                runOnUiThread(() -> {
                    resolving = false;
                    resolveNext();
                });
            }

            @Override
            @SuppressWarnings("deprecation")
            public void onServiceResolved(NsdServiceInfo info) {
                String host = info.getHost() == null ? null : info.getHost().getHostAddress();
                int port = info.getPort();
                String name = info.getServiceName();
                runOnUiThread(() -> {
                    resolving = false;
                    if (host != null && !host.contains(":")) addServer(name, "http://" + host + ":" + port);
                    resolveNext();
                });
            }
        });
    }

    private void addServer(String name, String url) {
        if (foundList == null || mode != Mode.SETUP || !shown.add(url)) return;
        View card = LayoutInflater.from(this).inflate(R.layout.item_server, foundList, false);
        String label = name.startsWith("Tapinion ") ? name.substring(9) : name;
        ((TextView) card.findViewById(R.id.server_name)).setText(getString(R.string.found_on, label));
        ((TextView) card.findViewById(R.id.server_address)).setText(url.replace("http://", ""));
        card.setOnClickListener(v -> connect(url));
        foundList.addView(card);
        if (searching != null) searching.setVisibility(View.GONE);
    }

    private void stopDiscovery() {
        if (discovery != null) {
            try {
                nsd.stopServiceDiscovery(discovery);
            } catch (Exception ignored) {
            }
            discovery = null;
        }
        toResolve.clear();
        resolving = false;
        if (multicastLock != null && multicastLock.isHeld()) multicastLock.release();
    }

    // --- Tapinion on the computer (web) ------------------------------------------

    /** Bridge for the kiosk page from the computer: hands over a kiosk for offline use. */
    private final class WebBridge {
        @JavascriptInterface
        public void kioskReady(String token, String kioskKey) {
            prefs.edit().putString(KEY_ACTIVE_KIOSK, token).apply();
            runOnUiThread(() -> {  // the kiosk is unlocked and running (not on the PIN page)
                kioskRunning = true;
                startPinning();
            });
            String o = origin;
            if (o == null || token == null || kioskKey == null || store.has(token)) return;
            background.execute(() -> {
                try {
                    store.pairAndDownload(o, token, kioskKey);
                    String instance = OfflineStore.instanceAt(o);
                    if (instance != null && !instance.isEmpty()) prefs.edit().putString(KEY_INSTANCE, instance).apply();
                    runOnUiThread(() -> Toast.makeText(MainActivity.this, R.string.offline_saved, Toast.LENGTH_SHORT).show());
                } catch (Exception ignored) {
                    // next time the kiosk opens
                }
            });
        }
    }

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    private void showWeb(String url) {
        stopDiscovery();
        mode = Mode.WEB;
        pageFinished = false;
        kioskRunning = false;
        foundList = offlineList = null;
        origin = originOf(url);
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);  // vote queue and device key of the web kiosk
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setTextZoom(100);
        s.setUserAgentString(s.getUserAgentString() + " TapinionKiosk/1.1");
        CookieManager.getInstance().setAcceptCookie(true);
        web.addJavascriptInterface(new WebBridge(), "TapinionApp");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri target = request.getUrl();
                if (originOf(target.toString()).equals(origin)) return false;
                if (!pinned) startActivity(new Intent(Intent.ACTION_VIEW, target));
                return true;
            }

            @Override
            public void onPageStarted(WebView view, String page, Bitmap favicon) {
                kioskRunning = false;
                pageFinished = false;
                main.removeCallbacks(pageWatchdog);
                main.postDelayed(pageWatchdog, PAGE_TIMEOUT_MS);
                updatePinning(page);
            }

            @Override
            public void onPageFinished(WebView view, String page) {
                pageFinished = true;
                webFailures = 0;
                main.removeCallbacks(pageWatchdog);
                if (isKioskPage(page)) {
                    prefs.edit().putString(KEY_LAST_KIOSK, page).apply();
                } else {
                    // A running kiosk only reaches other pages after the PIN (the server redirects
                    // to the login page, or to the setup wizard on a fresh installation).
                    if (isStartPage(page) || kioskActive(MainActivity.this)) {
                        view.clearHistory();  // "back" must not lead into a kiosk that was left with the PIN
                    }
                    prefs.edit().remove(KEY_LAST_KIOSK).remove(KEY_ACTIVE_KIOSK).apply();
                    stopPinning();
                }
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) unreachable(request.getUrl().toString());
            }
        });
        setContentView(web);
        showSystemBars(false);
        main.removeCallbacks(pageWatchdog);
        main.postDelayed(pageWatchdog, PAGE_TIMEOUT_MS);
        web.loadUrl(url);
    }

    /** The computer did not answer: check once more (new address?), else continue offline. */
    private void unreachable(String failedUrl) {
        if (mode != Mode.WEB) return;  // watchdog and error can both report the same failure
        main.removeCallbacks(pageWatchdog);
        stopPinning();
        webFailures++;
        if (webFailures >= 2) continueOffline(failedUrl);
        else showConnecting(failedUrl);
    }

    // --- offline kiosk and results (from the device) ------------------------------

    /** Bridge for the app's own offline pages. */
    private final class OfflineBridge {
        @JavascriptInterface public String bundle(String token) { return store.bundle(token); }
        @JavascriptInterface public String votes(String token) { return store.votesJson(token); }
        @JavascriptInterface public int pending(String token) { return store.pending(token); }
        @JavascriptInterface public boolean checkPin(String token, String pin) { return store.checkPin(token, pin); }

        @JavascriptInterface
        public void vote(String token, String value, String lang) {
            store.addVote(token, value, lang);
        }

        @JavascriptInterface
        public void kioskStarted(String token) {
            prefs.edit().putString(KEY_RUNNING_OFFLINE, token).putString(KEY_ACTIVE_KIOSK, token).apply();
            runOnUiThread(() -> {
                offlineStarted = true;
                startPinning();
            });
        }

        @JavascriptInterface
        public void exitKiosk(String token) {
            prefs.edit().remove(KEY_RUNNING_OFFLINE).remove(KEY_ACTIVE_KIOSK).remove(KEY_LAST_KIOSK).apply();
            runOnUiThread(() -> showSetup(null));
        }

        @JavascriptInterface
        public void close() {
            runOnUiThread(() -> showSetup(null));
        }
    }

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    private WebView offlineWebView() {
        WebView v = new WebView(this);
        WebSettings s = v.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setSupportZoom(false);
        s.setTextZoom(100);
        v.addJavascriptInterface(new OfflineBridge(), "TapinionApp");
        v.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return true;  // the offline pages never navigate away
            }
        });
        return v;
    }

    /** Run the kiosk of a stored event from the device; locked = ask for the PIN first. */
    private void showOfflineKiosk(String token, boolean locked) {
        stopDiscovery();
        main.removeCallbacks(pageWatchdog);
        mode = Mode.OFFLINE_KIOSK;
        offlineStarted = !locked;
        foundList = offlineList = null;
        web = null;
        WebView v = offlineWebView();
        setContentView(v);
        showSystemBars(false);
        v.loadUrl("file:///android_asset/offline/kiosk.html#" + Uri.encode(token) + (locked ? "&unlock=1" : ""));
        if (!locked) {
            prefs.edit().putString(KEY_RUNNING_OFFLINE, token).putString(KEY_ACTIVE_KIOSK, token).apply();
            startPinning();
        }
    }

    private void showResults(String token) {
        stopDiscovery();
        mode = Mode.RESULTS;
        foundList = offlineList = null;
        web = null;
        WebView v = offlineWebView();
        setContentView(v);
        showSystemBars(true);
        v.loadUrl("file:///android_asset/offline/results.html#" + Uri.encode(token));
    }

    /** Overview: full lock active (with a way to give the device back) or how to set it up. */
    private void renderLock(SwitchMaterial pin) {
        TextView status = findViewById(R.id.lock_status);
        TextView action = findViewById(R.id.lock_action);
        boolean owner = KioskLock.isOwner(this);
        pin.setVisibility(owner ? View.GONE : View.VISIBLE);
        status.setText(owner ? R.string.lock_full_on : R.string.lock_full_off);
        action.setText(owner ? R.string.lock_release : R.string.lock_how);
        action.setOnClickListener(v -> {
            if (owner) {
                new AlertDialog.Builder(this)
                        .setTitle(R.string.lock_release_question)
                        .setMessage(R.string.lock_release_text)
                        .setPositiveButton(R.string.lock_release, (d, w) -> {
                            try {
                                KioskLock.release(this);
                            } catch (Exception ignored) {
                            }
                            showSetup(null);
                        })
                        .setNegativeButton(android.R.string.cancel, null)
                        .show();
            } else {
                new AlertDialog.Builder(this)
                        .setTitle(R.string.lock_how_title)
                        .setMessage(getString(R.string.lock_how_text, "adb shell dpm set-device-owner "
                                + getPackageName() + "/.KioskAdmin"))
                        .setPositiveButton(android.R.string.ok, null)
                        .show();
            }
        });
    }

    // --- kiosk pinning, back key, system bars --------------------------------------

    /** Pinning starts when the unlocked kiosk reports itself (kioskReady), never on the PIN page. */
    private void updatePinning(String page) {
        if (!isKioskPage(page)) stopPinning();
    }

    private void startPinning() {
        if (pinned) return;
        boolean owner = KioskLock.isOwner(this);  // full lock: always on, cannot be switched off here
        if (!owner && !prefs.getBoolean(KEY_PIN_APP, true)) return;
        try {
            if (owner) KioskLock.engage(this);
            startLockTask();
            pinned = true;
        } catch (Exception ignored) {
            // pinning not allowed on this device
        }
    }

    private void stopPinning() {
        if (!pinned || prefs.getString(KEY_ACTIVE_KIOSK, null) != null) return;  // a running kiosk stays locked
        try {
            stopLockTask();
        } catch (Exception ignored) {
        }
        try {
            KioskLock.disengage(this);
        } catch (Exception ignored) {
        }
        pinned = false;
    }

    private void onBack() {
        switch (mode) {
            case OFFLINE_KIOSK:
                if (!offlineStarted) showSetup(null);  // still on the PIN screen: back to the overview
                return;  // a running kiosk is left with the PIN only
            case CONNECTING:
                cancelConnecting();
                return;
            case RESULTS:
                showSetup(null);
                return;
            case SETUP:
                if (prefs.getString(KEY_URL, null) != null) showConnecting(prefs.getString(KEY_URL, ""));
                else finishAndRemoveTask();
                return;
            default:
                break;
        }
        String path = web.getUrl() == null ? "" : Uri.parse(web.getUrl()).getPath();
        if (path != null && path.startsWith("/k/")) {
            // PIN page of a kiosk that is not running yet: back to the overview. A running kiosk, also
            // while a page reloads, is left with the PIN only (a hanging load ends after PAGE_TIMEOUT_MS).
            if (!kioskRunning && prefs.getString(KEY_ACTIVE_KIOSK, null) == null) showSetup(null);
            return;  // a running kiosk is left with the PIN only
        }
        if (!isStartPage(web.getUrl()) && web.canGoBack()) {
            web.goBack();
            return;
        }
        new AlertDialog.Builder(this)
                .setTitle(R.string.quit_question)
                .setPositiveButton(R.string.quit, (d, w) -> finishAndRemoveTask())
                .setNeutralButton(R.string.change_server, (d, w) -> showSetup(null))
                .setNegativeButton(android.R.string.cancel, null)
                .show();
    }

    private static String tokenOf(String kioskUrl) {
        if (kioskUrl == null) return null;
        String path = Uri.parse(kioskUrl).getPath();
        if (path == null) return null;
        String[] parts = path.split("/");
        return parts.length == 3 && parts[1].equals("k") ? parts[2] : null;
    }

    private static boolean isKioskPage(String page) {
        return tokenOf(page) != null;
    }

    private static boolean isStartPage(String page) {
        if (page == null) return false;
        String path = Uri.parse(page).getPath();
        return path == null || path.isEmpty() || path.equals("/") || path.equals("/login");
    }

    private void showSystemBars(boolean show) {
        WindowCompat.setDecorFitsSystemWindows(getWindow(), show);
        WindowInsetsControllerCompat c = WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());
        if (show) {
            c.show(WindowInsetsCompat.Type.systemBars());
        } else {
            c.hide(WindowInsetsCompat.Type.systemBars());
            c.setSystemBarsBehavior(WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus && (mode == Mode.WEB || mode == Mode.OFFLINE_KIOSK)) showSystemBars(false);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        background.shutdownNow();
    }
}
