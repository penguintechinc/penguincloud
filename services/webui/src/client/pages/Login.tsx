/**
 * Login page — thin wrapper over the shared-library `LoginPageBuilder`.
 * No custom login UI lives here; this file only supplies configuration and
 * hands the resulting token pair to the auth store.
 */

import { useCallback } from "react";
import { useNavigate, useLocation } from "react-router";
import { LoginPageBuilder } from "@penguintechinc/react-libs";
import type { LoginResponse } from "@penguintechinc/react-libs";
import { useAuth } from "../hooks/useAuth";
import { useSelfRegistrationEnabled } from "../hooks/useSelfRegistrationEnabled";

interface LocationState {
  from?: { pathname: string };
}

/**
 * BFF endpoint, not the portal API directly: `LoginPageBuilder` requires a
 * `success` flag and a 2xx MFA challenge that `/api/v1/auth/login` does not
 * emit. `src/server/authAdapter.ts` performs the translation.
 */
export const LOGIN_ENDPOINT = "/api/ui/login";

export default function Login() {
  const { establishSession } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  // Server-side default is closed (Config.ALLOW_SELF_REGISTRATION); this
  // mirrors it client-side rather than hardcoding a value that can
  // silently disagree with what the API actually does — see
  // useSelfRegistrationEnabled for the fail-closed behaviour when the
  // status endpoint is unreachable.
  const selfRegistrationEnabled = useSelfRegistrationEnabled();

  const from = (location.state as LocationState)?.from?.pathname || "/";

  const handleSuccess = useCallback(
    (response: LoginResponse) => {
      if (!response.token || !response.refreshToken) {
        console.log("[Login] Success without tokens { ignored: true }");
        return;
      }
      console.log("[Login] Authenticated { redirectTo:", from, "}");
      void establishSession(response.token, response.refreshToken).then(() => {
        navigate(from, { replace: true });
      });
    },
    [establishSession, navigate, from],
  );

  return (
    <LoginPageBuilder
      api={{
        loginUrl: LOGIN_ENDPOINT,
        method: "POST",
        headers: { Accept: "application/json" },
      }}
      branding={{
        appName: "PenguinCloud",
        tagline: "Unified control plane for the PenguinTech product line",
        githubRepo: "penguintechinc/penguincloud",
      }}
      onSuccess={handleSuccess}
      // The API verifies TOTP codes on the login endpoint, so the builder's
      // MFA prompt is wired up. CAPTCHA, passkey and GDPR consent have no
      // backing endpoints yet and stay off until they do (Phase 5).
      mfa={{ enabled: true, codeLength: 6, allowRememberDevice: false }}
      gdpr={{ enabled: false, privacyPolicyUrl: "" }}
      themeMode="dark"
      showForgotPassword={false}
      // Driven by the deployment's own ALLOW_SELF_REGISTRATION setting
      // (GET /api/v1/registration-status) rather than hardcoded false — an
      // operator who turns self-service signup ON now sees the button
      // appear. signUpUrl/onSignUp are left unset (default '#' navigation):
      // this SPA has no dedicated /register page yet, which is a separate,
      // pre-existing gap from the one this fix closes (button visibility
      // matching server capability).
      showSignUp={selfRegistrationEnabled}
      showRememberMe
      onError={(error, errorCode) => {
        console.log("[Login] Failed { errorCode:", errorCode ?? "none", "}");
        void error;
      }}
    />
  );
}
