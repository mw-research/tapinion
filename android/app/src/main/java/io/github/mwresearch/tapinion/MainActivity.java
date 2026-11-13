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
import android.view.LayoutInflater;
import android.view.View;
import android.view.WindowManager;
import android.view.inputmethod.EditorInfo;
import android.webkit.CookieManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

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
import java.util.HashSet;
import java.util.Set;

/**
 * Kiosk shell for Tapinion: finds Tapinion in the Wi-Fi by itself (or connects by QR code),
 * shows it full screen, keeps the screen on and can pin the app while a kiosk runs.
 * All logic, data and the PIN check stay on the computer or server.
 */
public class MainActivity extends AppCompatActivity {
    private static final String PREFS = "tapinion";
    private static final String KEY_URL = "url";
    private static final String KEY_PIN_APP = "pin_app";
    private static final String SERVICE_TYPE = "_tapinion._tcp";

    private SharedPreferences prefs;
    private WebView web;
    private String origin;
    private boolean pinned;

    // network discovery
    private NsdManager nsd;
    private NsdManager.DiscoveryListener discovery;
    private WifiManager.MulticastLock multicastLock;
    private final ArrayDeque<NsdServiceInfo> toResolve = new ArrayDeque<>();
    private boolean resolving;
    private final Set<String> shown = new HashSet<>();
    private LinearLayout foundList;
    private View searching;

    private final ActivityResultLauncher<ScanOptions> scanner = registerForActivityResult(new ScanContract(), result -> {
        if (result.getContents() != null) {
            connect(result.getContents().trim());
        }
    });

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        nsd = (NsdManager) getSystemService(Context.NSD_SERVICE);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                onBack();
            }
        });
        String url = prefs.getString(KEY_URL, null);
        if (url == null) {
            showSetup(null);
        } else {
            showWeb(url);
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        stopDiscovery();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (web == null && foundList != null) startDiscovery();
    }

    // --- start screen ---------------------------------------------------------

    private void showSetup(String error) {
        stopPinning();
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

        TextView err = findViewById(R.id.error);
        if (error != null) {
            err.setText(error);
            err.setVisibility(View.VISIBLE);
        }

        foundList = findViewById(R.id.found_list);
        searching = findViewById(R.id.searching);
        shown.clear();
        startDiscovery();
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
        prefs.edit().putString(KEY_URL, raw).apply();
        showWeb(raw);
    }

    // --- finding Tapinion in the Wi-Fi (DNS-SD "_tapinion._tcp") --------------

    private void startDiscovery() {
        if (discovery != null || nsd == null) return;
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
        if (foundList == null || web != null || !shown.add(url)) return;
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

    // --- web view -----------------------------------------------------------

    @SuppressLint("SetJavaScriptEnabled")
    private void showWeb(String url) {
        stopDiscovery();
        foundList = null;
        Uri uri = Uri.parse(url);
        origin = uri.getScheme() + "://" + uri.getAuthority();
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);  // offline vote queue
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setTextZoom(100);
        s.setUserAgentString(s.getUserAgentString() + " TapinionKiosk/1.0");
        CookieManager.getInstance().setAcceptCookie(true);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri target = request.getUrl();
                String o = target.getScheme() + "://" + target.getAuthority();
                if (o.equals(origin)) return false;
                if (!pinned) startActivity(new Intent(Intent.ACTION_VIEW, target));
                return true;
            }

            @Override
            public void onPageStarted(WebView view, String page, Bitmap favicon) {
                updatePinning(page);
            }

            @Override
            public void onPageFinished(WebView view, String page) {
                // On the start/login page (e.g. after leaving the kiosk with the PIN) "back" must not
                // lead into the kiosk again: forget the history, so back offers to quit the app.
                if (isStartPage(page)) view.clearHistory();
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showOffline();
            }
        });
        setContentView(web);
        showSystemBars(false);
        web.loadUrl(url);
    }

    private void showOffline() {
        stopPinning();
        web = null;
        setContentView(R.layout.activity_offline);
        showSystemBars(true);
        String url = prefs.getString(KEY_URL, "");
        ((TextView) findViewById(R.id.offline_text)).setText(getString(R.string.offline, url.replace("http://", "")));
        findViewById(R.id.retry).setOnClickListener(v -> showWeb(prefs.getString(KEY_URL, "")));
        findViewById(R.id.change).setOnClickListener(v -> showSetup(null));
        View root = findViewById(R.id.retry);
        root.postDelayed(() -> {
            if (web == null && root.isAttachedToWindow()) showWeb(prefs.getString(KEY_URL, ""));
        }, 15000);
    }

    /** Pin the app while a kiosk page is open (leaving needs the PIN in the page). */
    private void updatePinning(String page) {
        String path = page == null ? null : Uri.parse(page).getPath();
        boolean kiosk = path != null && path.startsWith("/k/");
        if (kiosk && prefs.getBoolean(KEY_PIN_APP, true) && !pinned) {
            try {
                startLockTask();
                pinned = true;
            } catch (Exception ignored) {
                // pinning not allowed on this device
            }
        } else if (!kiosk) {
            stopPinning();
        }
    }

    private void stopPinning() {
        if (!pinned) return;
        try {
            stopLockTask();
        } catch (Exception ignored) {
        }
        pinned = false;
    }

    private void onBack() {
        if (web == null) {
            if (prefs.getString(KEY_URL, null) != null) showWeb(prefs.getString(KEY_URL, ""));
            return;
        }
        String path = web.getUrl() == null ? "" : Uri.parse(web.getUrl()).getPath();
        if (path != null && path.startsWith("/k/")) return;  // the kiosk is left with the PIN only
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
        if (hasFocus && web != null) showSystemBars(false);
    }
}
