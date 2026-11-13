// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
package io.github.mwresearch.tapinion;

import android.annotation.SuppressLint;
import android.app.ActivityManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

import com.journeyapps.barcodescanner.ScanContract;
import com.journeyapps.barcodescanner.ScanOptions;

/**
 * Kiosk shell for Tapinion: connects to a Tapinion server (laptop or server in the network),
 * shows it full screen, keeps the screen on and can pin the app while a kiosk runs.
 * All logic, data and the PIN check stay on the server.
 */
public class MainActivity extends AppCompatActivity {
    private static final String PREFS = "tapinion";
    private static final String KEY_URL = "url";
    private static final String KEY_PIN_APP = "pin_app";

    private SharedPreferences prefs;
    private WebView web;
    private String origin;
    private boolean pinned;

    private final ActivityResultLauncher<ScanOptions> scanner = registerForActivityResult(new ScanContract(), result -> {
        if (result.getContents() != null) {
            connect(result.getContents().trim());
        }
    });

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
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

    // --- setup screen -----------------------------------------------------

    private void showSetup(String error) {
        stopPinning();
        web = null;
        int pad = dp(24);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(pad, pad, pad, pad);
        box.setGravity(Gravity.CENTER_HORIZONTAL);

        TextView title = new TextView(this);
        title.setText(R.string.setup_title);
        title.setTextSize(26);
        title.setTextColor(Color.rgb(14, 116, 144));
        box.addView(title);

        TextView intro = new TextView(this);
        intro.setText(R.string.setup_intro);
        intro.setTextSize(16);
        intro.setPadding(0, dp(12), 0, dp(16));
        box.addView(intro);

        Button scan = new Button(this);
        scan.setText(R.string.setup_scan);
        scan.setOnClickListener(v -> {
            ScanOptions options = new ScanOptions();
            options.setDesiredBarcodeFormats(ScanOptions.QR_CODE);
            options.setPrompt(getString(R.string.setup_scan_prompt));
            options.setBeepEnabled(false);
            options.setOrientationLocked(false);
            scanner.launch(options);
        });
        box.addView(scan, full());

        TextView or = new TextView(this);
        or.setText(R.string.setup_or);
        or.setPadding(0, dp(16), 0, dp(4));
        box.addView(or);

        EditText input = new EditText(this);
        input.setHint("http://192.168.0.10:8765");
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        input.setSingleLine(true);
        String current = prefs.getString(KEY_URL, null);
        if (current != null) input.setText(current);
        box.addView(input, full());

        CheckBox pin = new CheckBox(this);
        pin.setText(R.string.setup_pin_app);
        pin.setChecked(prefs.getBoolean(KEY_PIN_APP, true));
        pin.setOnCheckedChangeListener((b, checked) -> prefs.edit().putBoolean(KEY_PIN_APP, checked).apply());
        box.addView(pin, full());

        Button go = new Button(this);
        go.setText(R.string.setup_connect);
        go.setOnClickListener(v -> connect(input.getText().toString().trim()));
        box.addView(go, full());

        if (error != null) {
            TextView err = new TextView(this);
            err.setText(error);
            err.setTextColor(Color.rgb(214, 69, 69));
            err.setPadding(0, dp(12), 0, 0);
            box.addView(err);
        }

        TextView about = new TextView(this);
        about.setText(getString(R.string.setup_about));
        about.setTextSize(12);
        about.setTextColor(Color.GRAY);
        about.setPadding(0, dp(24), 0, 0);
        box.addView(about);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(box);
        scroll.setBackgroundColor(Color.WHITE);
        setContentView(scroll);
        showSystemBars(true);
    }

    private void connect(String raw) {
        if (raw.isEmpty()) return;
        if (!raw.startsWith("http://") && !raw.startsWith("https://")) raw = "http://" + raw;
        Uri uri = Uri.parse(raw);
        if (uri.getHost() == null) {
            showSetup(getString(R.string.setup_invalid));
            return;
        }
        prefs.edit().putString(KEY_URL, raw).apply();
        showWeb(raw);
    }

    // --- web view -----------------------------------------------------------

    @SuppressLint("SetJavaScriptEnabled")
    private void showWeb(String url) {
        Uri uri = Uri.parse(url);
        origin = uri.getScheme() + "://" + uri.getAuthority();
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);  // offline vote queue
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setTextZoom(100);
        s.setMediaPlaybackRequiresUserGesture(true);
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
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    showOffline();
                }
            }
        });
        setContentView(web);
        showSystemBars(false);
        web.loadUrl(url);
    }

    private void showOffline() {
        stopPinning();
        int pad = dp(32);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setPadding(pad, pad, pad, pad);
        box.setBackgroundColor(Color.WHITE);
        TextView msg = new TextView(this);
        msg.setText(getString(R.string.offline, prefs.getString(KEY_URL, "")));
        msg.setTextSize(18);
        msg.setGravity(Gravity.CENTER);
        box.addView(msg);
        Button retry = new Button(this);
        retry.setText(R.string.retry);
        retry.setOnClickListener(v -> showWeb(prefs.getString(KEY_URL, "")));
        box.addView(retry, wrap());
        Button change = new Button(this);
        change.setText(R.string.change_server);
        change.setOnClickListener(v -> showSetup(null));
        box.addView(change, wrap());
        setContentView(box);
        web = null;
        box.postDelayed(() -> {
            if (web == null && box.isAttachedToWindow()) showWeb(prefs.getString(KEY_URL, ""));
        }, 15000);
    }

    /** Pin the app while a kiosk page is open (leaving needs the PIN in the page). */
    private void updatePinning(String page) {
        boolean kiosk = page != null && Uri.parse(page).getPath() != null && Uri.parse(page).getPath().startsWith("/k/");
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
        if (web.canGoBack()) {
            web.goBack();
            return;
        }
        new AlertDialog.Builder(this)
                .setMessage(R.string.change_server_question)
                .setPositiveButton(R.string.change_server, (d, w) -> showSetup(null))
                .setNegativeButton(android.R.string.cancel, null)
                .show();
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

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    private LinearLayout.LayoutParams full() {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        p.topMargin = dp(8);
        return p;
    }

    private LinearLayout.LayoutParams wrap() {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        p.topMargin = dp(12);
        return p;
    }
}
