// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
package io.github.mwresearch.tapinion;

import android.app.admin.DeviceAdminReceiver;

/** Makes the app eligible as device owner for the full kiosk lock (see KioskLock). */
public final class KioskAdmin extends DeviceAdminReceiver { }
