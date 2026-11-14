// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
package io.github.mwresearch.tapinion;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;

/**
 * Events stored on the device for offline use. Every kiosk opened in the app is kept here
 * (question, design, logo, PIN check). Ratings collected offline wait here and are sent to the
 * computer once it is reachable; each rating has an id, so sending twice is harmless.
 *
 * Layout: files/offline/<token>/{bundle.json, meta.json, votes.json}
 */
final class OfflineStore {
    static final class Entry {
        String token, name, date, mode, origin, device, instance, syncedAt;
        boolean active, switchedOff;
        int pending;
    }

    static final class SyncResult {
        int sent, events;
        boolean reachable;
    }

    private final File root;

    OfflineStore(Context context) {
        root = new File(context.getFilesDir(), "offline");
        //noinspection ResultOfMethodCallIgnored
        root.mkdirs();
    }

    // --- events -------------------------------------------------------------

    synchronized void save(String token, String origin, String device, String bundleJson) throws JSONException {
        JSONObject bundle = new JSONObject(bundleJson);
        File dir = dir(token);
        //noinspection ResultOfMethodCallIgnored
        dir.mkdirs();
        write(new File(dir, "bundle.json"), bundleJson);
        JSONObject meta = readJson(new File(dir, "meta.json"), new JSONObject());
        meta.put("origin", origin);
        meta.put("device", device);
        meta.put("instance", bundle.getJSONObject("server").optString("instance"));
        meta.put("synced_at", now());
        meta.put("switched_off", false);
        write(new File(dir, "meta.json"), meta.toString());
    }

    synchronized boolean has(String token) {
        return new File(dir(token), "bundle.json").isFile();
    }

    synchronized String bundle(String token) {
        return read(new File(dir(token), "bundle.json"), "{}");
    }

    synchronized List<Entry> list() {
        List<Entry> out = new ArrayList<>();
        File[] dirs = root.listFiles();
        if (dirs == null) return out;
        for (File d : dirs) {
            try {
                JSONObject b = new JSONObject(read(new File(d, "bundle.json"), "{}"));
                JSONObject m = readJson(new File(d, "meta.json"), new JSONObject());
                JSONObject ev = b.getJSONObject("event");
                Entry e = new Entry();
                e.token = d.getName();
                e.name = ev.optString("name");
                e.date = ev.optString("date");
                e.mode = ev.optString("mode");
                e.active = ev.optBoolean("active", true);
                e.origin = m.optString("origin");
                e.device = m.optString("device");
                e.instance = m.optString("instance");
                e.syncedAt = m.optString("synced_at");
                e.switchedOff = m.optBoolean("switched_off", false);
                e.pending = unsent(e.token).length();
                out.add(e);
            } catch (JSONException ignored) {
                // a broken entry is skipped
            }
        }
        out.sort((a, b) -> b.date.compareTo(a.date));
        return out;
    }

    synchronized void remove(String token) {
        File d = dir(token);
        File[] files = d.listFiles();
        if (files != null) for (File f : files) //noinspection ResultOfMethodCallIgnored
            f.delete();
        //noinspection ResultOfMethodCallIgnored
        d.delete();
    }

    /** The computer got a new address: move all its events there. */
    synchronized void moveOrigin(String instance, String newOrigin) {
        for (Entry e : list()) {
            if (instance.equals(e.instance) && !newOrigin.equals(e.origin)) {
                File f = new File(dir(e.token), "meta.json");
                JSONObject m = readJson(f, new JSONObject());
                try {
                    m.put("origin", newOrigin);
                    write(f, m.toString());
                } catch (JSONException ignored) {
                }
            }
        }
    }

    // --- ratings ------------------------------------------------------------

    synchronized void addVote(String token, String value, String lang) {
        try {
            JSONArray votes = votes(token);
            JSONObject v = new JSONObject();
            v.put("id", UUID.randomUUID().toString());
            v.put("value", value);
            v.put("lang", lang);
            v.put("ts", now());
            v.put("sent", false);
            votes.put(v);
            write(new File(dir(token), "votes.json"), votes.toString());
        } catch (JSONException ignored) {
        }
    }

    synchronized int pending(String token) {
        return unsent(token).length();
    }

    /** All ratings collected on this device for the event (for the results screen). */
    synchronized String votesJson(String token) {
        return votes(token).toString();
    }

    private synchronized JSONArray unsent(String token) {
        JSONArray all = votes(token), out = new JSONArray();
        for (int i = 0; i < all.length(); i++) {
            JSONObject v = all.optJSONObject(i);
            if (v != null && !v.optBoolean("sent", false)) {
                try {
                    out.put(new JSONObject().put("id", v.optString("id")).put("value", v.optString("value"))
                            .put("ts", v.optString("ts")).put("lang", v.optString("lang")));
                } catch (JSONException ignored) {
                }
            }
        }
        return out;
    }

    synchronized boolean checkPin(String token, String pin) {
        try {
            JSONObject p = new JSONObject(bundle(token)).getJSONObject("event").getJSONObject("pin");
            String expected = p.optString("sha256");
            if (expected.isEmpty() || pin == null || pin.isEmpty()) return false;
            byte[] d = MessageDigest.getInstance("SHA-256").digest((p.optString("salt") + pin).getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (byte x : d) hex.append(String.format("%02x", x));
            return MessageDigest.isEqual(hex.toString().getBytes(StandardCharsets.UTF_8), expected.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            return false;
        }
    }

    private synchronized void markSent(String token, Set<String> accepted, Set<String> rejected) {
        JSONArray votes = votes(token);
        for (int i = 0; i < votes.length(); i++) {
            JSONObject v = votes.optJSONObject(i);
            if (v == null) continue;
            String id = v.optString("id");
            try {
                if (accepted.contains(id)) v.put("sent", true);
                if (rejected.contains(id)) v.put("sent", true).put("rejected", true);
            } catch (JSONException ignored) {
            }
        }
        write(new File(dir(token), "votes.json"), votes.toString());
    }

    // --- synchronisation (call off the main thread) --------------------------

    /** Instance id of the Tapinion at this address, or null if it is not reachable. */
    static String instanceAt(String origin) {
        try {
            String body = http("GET", origin + "/healthz", null, null, 3000);
            return body == null ? null : new JSONObject(body).optString("instance", "");
        } catch (Exception e) {
            return null;
        }
    }

    /** Keep an event for offline use: own device key (paired with the kiosk's key), then download. */
    void pairAndDownload(String origin, String token, String kioskKey) throws Exception {
        String body = http("POST", origin + "/api/kiosk/" + token + "/pair", kioskKey, "{}", 8000);
        if (body == null) throw new IOException("no answer");
        download(origin, token, new JSONObject(body).getString("device"));
    }

    /** Download the event data for a kiosk this device runs (after it was opened in the app). */
    void download(String origin, String token, String device) throws Exception {
        String body = http("GET", origin + "/api/kiosk/" + token, device, null, 8000);
        if (body == null) throw new IOException("no answer");
        save(token, origin, device, body);
    }

    /** Send waiting ratings and refresh the event data of every stored event that is reachable. */
    SyncResult syncAll() {
        SyncResult r = new SyncResult();
        Set<String> unreachable = new HashSet<>();
        for (Entry e : list()) {
            if (e.origin.isEmpty() || unreachable.contains(e.origin)) continue;
            if (instanceAt(e.origin) == null) {
                unreachable.add(e.origin);
                continue;
            }
            r.reachable = true;
            r.events++;
            try {
                JSONArray votes = unsent(e.token);
                if (votes.length() > 0) {
                    JSONObject payload = new JSONObject().put("votes", votes);
                    String body = http("POST", e.origin + "/api/kiosk/" + e.token + "/votes", e.device, payload.toString(), 15000);
                    if (body != null) {
                        JSONObject res = new JSONObject(body);
                        Set<String> accepted = new HashSet<>(), rejected = new HashSet<>();
                        JSONArray acc = res.optJSONArray("accepted");
                        JSONArray rej = res.optJSONArray("rejected");
                        for (int i = 0; acc != null && i < acc.length(); i++) accepted.add(acc.getString(i));
                        for (int i = 0; rej != null && i < rej.length(); i++) rejected.add(rej.getString(i));  // never accepted
                        r.sent += accepted.size();
                        markSent(e.token, accepted, rejected);
                    }
                }
                download(e.origin, e.token, e.device);
            } catch (HttpError err) {
                if (err.status == 403 || err.status == 404) markSwitchedOff(e.token);
            } catch (Exception ignored) {
                // try again next time
            }
        }
        return r;
    }

    private synchronized void markSwitchedOff(String token) {
        File f = new File(dir(token), "meta.json");
        JSONObject m = readJson(f, new JSONObject());
        try {
            m.put("switched_off", true);
            write(f, m.toString());
        } catch (JSONException ignored) {
        }
    }

    // --- helpers --------------------------------------------------------------

    static final class HttpError extends IOException {
        final int status;

        HttpError(int status) {
            super("HTTP " + status);
            this.status = status;
        }
    }

    private static String http(String method, String url, String device, String json, int timeoutMs) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        try {
            c.setRequestMethod(method);
            c.setConnectTimeout(Math.min(timeoutMs, 4000));
            c.setReadTimeout(timeoutMs);
            if (device != null) c.setRequestProperty("X-Kiosk-Device", device);
            if (json != null) {
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/json");
                try (OutputStream o = c.getOutputStream()) {
                    o.write(json.getBytes(StandardCharsets.UTF_8));
                }
            }
            int status = c.getResponseCode();
            if (status >= 400) throw new HttpError(status);
            return new String(readAll(c.getInputStream()), StandardCharsets.UTF_8);
        } finally {
            c.disconnect();
        }
    }

    private File dir(String token) {
        return new File(root, token.replaceAll("[^A-Za-z0-9_-]", "_"));
    }

    private JSONArray votes(String token) {
        try {
            return new JSONArray(read(new File(dir(token), "votes.json"), "[]"));
        } catch (JSONException e) {
            return new JSONArray();
        }
    }

    private static String now() {
        return new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.ROOT).format(new Date());
    }

    private static JSONObject readJson(File f, JSONObject fallback) {
        try {
            return new JSONObject(read(f, "{}"));
        } catch (JSONException e) {
            return fallback;
        }
    }

    private static String read(File f, String fallback) {
        if (!f.isFile()) return fallback;
        try (InputStream in = new FileInputStream(f)) {
            return new String(readAll(in), StandardCharsets.UTF_8);
        } catch (IOException e) {
            return fallback;
        }
    }

    /** Write via a temporary file, so a power cut never leaves a half-written file. */
    private static void write(File f, String text) {
        File tmp = new File(f.getPath() + ".tmp");
        try (OutputStream o = new FileOutputStream(tmp)) {
            o.write(text.getBytes(StandardCharsets.UTF_8));
            o.flush();
        } catch (IOException e) {
            return;
        }
        //noinspection ResultOfMethodCallIgnored
        tmp.renameTo(f);
    }

    private static byte[] readAll(InputStream in) throws IOException {
        try (ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[16384];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            return out.toByteArray();
        }
    }
}
