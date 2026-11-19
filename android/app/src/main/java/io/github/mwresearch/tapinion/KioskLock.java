// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
package io.github.mwresearch.tapinion;

import android.app.Activity;
import android.app.admin.DevicePolicyManager;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.UserManager;

/**
 * Full kiosk lock. When the app is the device owner (set up once per tablet, see README), a
 * running kiosk cannot be left at all: no home, no recent apps, no notifications, no power
 * menu, no unpinning, no safe mode, and after a restart the device opens the kiosk again.
 * Without device owner the app falls back to Android's screen pinning.
 */
final class KioskLock {

    /** After a restart: a kiosk that was running in full lock opens again by itself. */
    public static final class Boot extends BroadcastReceiver {
        @Override
        public void onReceive(Context c, Intent intent) {
            if (!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction()) || !isOwner(c)) return;
            if (!MainActivity.kioskActive(c)) return;
            c.startActivity(new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        }
    }

    private KioskLock() { }

    static ComponentName admin(Context c) {
        return new ComponentName(c, KioskAdmin.class);
    }

    private static DevicePolicyManager dpm(Context c) {
        return (DevicePolicyManager) c.getSystemService(Context.DEVICE_POLICY_SERVICE);
    }

    static boolean isOwner(Context c) {
        return dpm(c).isDeviceOwnerApp(c.getPackageName());
    }

    /** Before startLockTask: silent, full lock task mode without home, recents, notifications or power menu. */
    static void engage(Activity a) {
        if (!isOwner(a)) return;
        DevicePolicyManager d = dpm(a);
        ComponentName adm = admin(a);
        d.setLockTaskPackages(adm, new String[]{a.getPackageName()});
        if (Build.VERSION.SDK_INT >= 28) d.setLockTaskFeatures(adm, DevicePolicyManager.LOCK_TASK_FEATURE_NONE);
        d.addUserRestriction(adm, UserManager.DISALLOW_SAFE_BOOT);
    }

    /** After the kiosk was left with the PIN: the device behaves normally again. */
    static void disengage(Context c) {
        if (!isOwner(c)) return;
        DevicePolicyManager d = dpm(c);
        ComponentName adm = admin(c);
        d.clearUserRestriction(adm, UserManager.DISALLOW_SAFE_BOOT);
    }

    /** Give the device back: the app is no longer device owner and can be uninstalled. */
    static void release(Context c) {
        if (!isOwner(c)) return;
        disengage(c);
        DevicePolicyManager d = dpm(c);
        d.setLockTaskPackages(admin(c), new String[0]);
        d.clearDeviceOwnerApp(c.getPackageName());
    }
}
