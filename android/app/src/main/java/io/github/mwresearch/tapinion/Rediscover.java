// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
package io.github.mwresearch.tapinion;

import android.content.Context;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.net.wifi.WifiManager;

import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Finds a known Tapinion installation in the Wi-Fi again when its address changed (e.g. the
 * laptop got a new IP address). Every installation announces a fixed id ("instance").
 * Blocking – call off the main thread.
 */
final class Rediscover {
    private static final String SERVICE_TYPE = "_tapinion._tcp";

    private Rediscover() {
    }

    /** "http://host:port" of the installation with this id, or null if not found in time. */
    @SuppressWarnings("deprecation")
    static String find(Context context, String instance, long timeoutMs) {
        if (instance == null || instance.isEmpty()) return null;
        NsdManager nsd = (NsdManager) context.getSystemService(Context.NSD_SERVICE);
        if (nsd == null) return null;
        WifiManager.MulticastLock lock = null;
        try {
            WifiManager wifi = (WifiManager) context.getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            if (wifi != null) {
                lock = wifi.createMulticastLock("tapinion-rediscover");
                lock.setReferenceCounted(false);
                lock.acquire();
            }
        } catch (Exception ignored) {
        }

        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<String> found = new AtomicReference<>();
        ArrayDeque<NsdServiceInfo> queue = new ArrayDeque<>();
        final boolean[] resolving = {false};

        final Runnable[] next = new Runnable[1];
        next[0] = () -> {
            NsdServiceInfo info;
            synchronized (queue) {
                if (resolving[0] || queue.isEmpty() || done.getCount() == 0) return;
                resolving[0] = true;
                info = queue.poll();
            }
            nsd.resolveService(info, new NsdManager.ResolveListener() {
                @Override
                public void onResolveFailed(NsdServiceInfo i, int code) {
                    synchronized (queue) { resolving[0] = false; }
                    next[0].run();
                }

                @Override
                public void onServiceResolved(NsdServiceInfo i) {
                    Map<String, byte[]> attrs = i.getAttributes();
                    byte[] id = attrs == null ? null : attrs.get("instance");
                    String host = i.getHost() == null ? null : i.getHost().getHostAddress();
                    if (id != null && instance.equals(new String(id, StandardCharsets.UTF_8))
                            && host != null && !host.contains(":")) {
                        found.set("http://" + host + ":" + i.getPort());
                        done.countDown();
                    }
                    synchronized (queue) { resolving[0] = false; }
                    next[0].run();
                }
            });
        };

        NsdManager.DiscoveryListener listener = new NsdManager.DiscoveryListener() {
            @Override public void onDiscoveryStarted(String type) { }
            @Override public void onDiscoveryStopped(String type) { }
            @Override public void onStartDiscoveryFailed(String type, int code) { done.countDown(); }
            @Override public void onStopDiscoveryFailed(String type, int code) { }
            @Override public void onServiceLost(NsdServiceInfo info) { }

            @Override
            public void onServiceFound(NsdServiceInfo info) {
                synchronized (queue) { queue.add(info); }
                next[0].run();
            }
        };
        try {
            nsd.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, listener);
            done.await(timeoutMs, TimeUnit.MILLISECONDS);
        } catch (Exception ignored) {
        } finally {
            try {
                nsd.stopServiceDiscovery(listener);
            } catch (Exception ignored) {
            }
            if (lock != null && lock.isHeld()) lock.release();
        }
        return found.get();
    }
}
