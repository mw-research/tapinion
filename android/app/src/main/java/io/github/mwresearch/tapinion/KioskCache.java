// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
package io.github.mwresearch.tapinion;

import android.content.Context;
import android.net.Uri;
import android.webkit.CookieManager;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Keeps the running kiosk on the device: the kiosk page, its voting form, styles, scripts and the
 * logo. When the computer running Tapinion is out of reach (e.g. the tablet was prepared in the
 * office and restarts at the venue), the kiosk opens from here; votes wait on the device and are
 * sent as soon as the computer is reachable again. Only working (unlocked) kiosk screens are kept.
 */
final class KioskCache {
    private static final int CONNECT_TIMEOUT_MS = 4000;
    private static final int READ_TIMEOUT_MS = 8000;

    private final File dir;

    KioskCache(Context context) {
        dir = new File(context.getCacheDir(), "kiosk");
        //noinspection ResultOfMethodCallIgnored
        dir.mkdirs();
    }

    /** Requests worth keeping: kiosk page and form, static files, logo. */
    static boolean cacheable(Uri url) {
        String path = url.getPath();
        if (path == null) return false;
        if (path.startsWith("/static/") || path.equals("/branding/logo")) return true;
        if (!path.startsWith("/k/")) return false;
        String[] parts = path.split("/");  // "", "k", token[, "form"]
        return parts.length == 3 || (parts.length == 4 && parts[3].equals("form"));
    }

    /** Fetch from the network (keeping a copy) or, if that fails, answer from the device. */
    WebResourceResponse handle(WebResourceRequest request) {
        Uri url = request.getUrl();
        String key = key(url);
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(url.toString()).openConnection();
            conn.setConnectTimeout(CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(READ_TIMEOUT_MS);
            conn.setInstanceFollowRedirects(false);
            for (Map.Entry<String, String> h : request.getRequestHeaders().entrySet()) {
                conn.setRequestProperty(h.getKey(), h.getValue());
            }
            String cookies = CookieManager.getInstance().getCookie(url.toString());
            if (cookies != null) conn.setRequestProperty("Cookie", cookies);

            int status = conn.getResponseCode();
            List<String> setCookies = conn.getHeaderFields().get("Set-Cookie");
            if (setCookies != null) {
                for (String c : setCookies) CookieManager.getInstance().setCookie(url.toString(), c);
            }
            if (status >= 300 && status < 400) {
                return null;  // let the WebView follow redirects itself
            }
            if (status >= 500) throw new IOException("server error " + status);

            byte[] body = readAll(status >= 400 ? conn.getErrorStream() : conn.getInputStream());
            String type = conn.getContentType() == null ? "text/html; charset=utf-8" : conn.getContentType();
            String mime = type.split(";")[0].trim();
            String charset = charsetOf(type);
            boolean page = url.getPath() != null && url.getPath().startsWith("/k/") && !url.getPath().endsWith("/form");
            boolean keep = status == 200 && (!page || "unlocked".equals(conn.getHeaderField("X-Kiosk-State")));
            if (keep) store(key, mime, charset, body);

            Map<String, String> headers = new HashMap<>();
            headers.put("Cache-Control", "no-store");
            String reason = conn.getResponseMessage() == null ? "OK" : conn.getResponseMessage();
            return new WebResourceResponse(mime, charset, status, reason, headers, new ByteArrayInputStream(body));
        } catch (IOException e) {
            return fromDevice(key);  // null if nothing kept: the WebView shows its own error
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    boolean has(Uri url) {
        return new File(dir, key(url) + ".body").isFile();
    }

    void clear() {
        File[] files = dir.listFiles();
        if (files != null) for (File f : files) //noinspection ResultOfMethodCallIgnored
            f.delete();
    }

    // --- storage ------------------------------------------------------------

    private WebResourceResponse fromDevice(String key) {
        File body = new File(dir, key + ".body");
        File meta = new File(dir, key + ".meta");
        if (!body.isFile() || !meta.isFile()) return null;
        try {
            String[] m = new String(readAll(new FileInputStream(meta)), StandardCharsets.UTF_8).split("\n");
            Map<String, String> headers = new HashMap<>();
            headers.put("Cache-Control", "no-store");
            return new WebResourceResponse(m[0], m.length > 1 && !m[1].isEmpty() ? m[1] : null, 200, "OK", headers,
                    new FileInputStream(body));
        } catch (IOException e) {
            return null;
        }
    }

    private void store(String key, String mime, String charset, byte[] body) {
        try (FileOutputStream b = new FileOutputStream(new File(dir, key + ".body"));
             FileOutputStream m = new FileOutputStream(new File(dir, key + ".meta"))) {
            b.write(body);
            m.write((mime + "\n" + (charset == null ? "" : charset)).getBytes(StandardCharsets.UTF_8));
        } catch (IOException ignored) {
            // a full disk only costs the offline copy
        }
    }

    /** The query string is ignored (?v=…, ?lang=…), so a kiosk page is found in any language. */
    private static String key(Uri url) {
        String s = url.getScheme() + "://" + url.getAuthority() + url.getPath();
        try {
            byte[] d = MessageDigest.getInstance("SHA-1").digest(s.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (byte x : d) hex.append(String.format("%02x", x));
            return hex.toString();
        } catch (Exception e) {
            return Integer.toHexString(s.hashCode());
        }
    }

    private static String charsetOf(String contentType) {
        for (String part : contentType.split(";")) {
            String p = part.trim();
            if (p.toLowerCase().startsWith("charset=")) return p.substring(8).replace("\"", "");
        }
        return contentType.startsWith("text/") ? "utf-8" : null;
    }

    private static byte[] readAll(InputStream in) throws IOException {
        if (in == null) return new byte[0];
        try (InputStream input = in; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[16384];
            int n;
            while ((n = input.read(buf)) > 0) out.write(buf, 0, n);
            return out.toByteArray();
        }
    }
}
