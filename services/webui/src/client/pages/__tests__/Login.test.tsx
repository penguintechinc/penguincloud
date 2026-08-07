/**
 * Login page tests.
 *
 * The page itself is configuration only — these assert that the shared-library
 * component is what renders, that it is pointed at the BFF adapter, and that a
 * successful response reaches the auth store and the router.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useNavigate, useLocation } from "react-router";
import Login, { LOGIN_ENDPOINT } from "../Login";
import { useAuthStore } from "../../hooks/useAuth";

const establishSession = jest.fn(() => Promise.resolve());
const navigate = jest.fn();

jest.mock("../../hooks/useAuth", () => {
  const actual = jest.requireActual("../../hooks/useAuth");
  return {
    ...actual,
    useAuth: () => ({ establishSession }),
  };
});

/** Body posted by LoginPageBuilder, captured from the fetch mock. */
function lastRequest(): { url: string; body: Record<string, unknown> } {
  const mock = global.fetch as unknown as jest.Mock;
  const [url, init] = mock.mock.calls[mock.mock.calls.length - 1];
  return { url, body: JSON.parse(init.body) };
}

function mockFetchOnce(status: number, payload: unknown) {
  (global.fetch as unknown as jest.Mock).mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(payload),
  });
}

const SUCCESS_PAYLOAD = {
  success: true,
  token: "access-abc",
  refreshToken: "refresh-def",
  user: { id: "1", email: "a@b.test", name: "Ada", roles: ["admin"] },
};

describe("Login", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.clear();
    global.fetch = jest.fn() as unknown as typeof fetch;
    (useNavigate as unknown as jest.Mock).mockReturnValue(navigate);
    (useLocation as unknown as jest.Mock).mockReturnValue({
      pathname: "/login",
    });
  });

  it("renders the shared-library login page, not a bespoke form", () => {
    render(<Login />);

    expect(screen.getByText("PenguinCloud")).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("hides sign-up and forgot-password links that have no route", () => {
    render(<Login />);

    expect(screen.queryByText(/forgot password/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/sign up/i)).not.toBeInTheDocument();
  });

  it("submits credentials to the BFF adapter endpoint", async () => {
    mockFetchOnce(200, SUCCESS_PAYLOAD);
    render(<Login />);

    await userEvent.type(screen.getByLabelText(/email/i), "a@b.test");
    await userEvent.type(screen.getByLabelText(/password/i), "pw");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    const { url, body } = lastRequest();
    expect(url).toBe(LOGIN_ENDPOINT);
    expect(url).toBe("/api/ui/login");
    expect(body.email).toBe("a@b.test");
    expect(body.password).toBe("pw");
  });

  it("establishes the session and redirects on success", async () => {
    mockFetchOnce(200, SUCCESS_PAYLOAD);
    render(<Login />);

    await userEvent.type(screen.getByLabelText(/email/i), "a@b.test");
    await userEvent.type(screen.getByLabelText(/password/i), "pw");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() =>
      expect(establishSession).toHaveBeenCalledWith(
        "access-abc",
        "refresh-def",
      ),
    );
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith("/", { replace: true }),
    );
  });

  it("ignores a success response that carries no tokens", async () => {
    mockFetchOnce(200, { success: true });
    render(<Login />);

    await userEvent.type(screen.getByLabelText(/email/i), "a@b.test");
    await userEvent.type(screen.getByLabelText(/password/i), "pw");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    expect(establishSession).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("surfaces the adapter's error message without redirecting", async () => {
    mockFetchOnce(401, {
      success: false,
      error: "Invalid email or password",
      errorCode: "AUTH_FAILED",
    });
    render(<Login />);

    await userEvent.type(screen.getByLabelText(/email/i), "a@b.test");
    await userEvent.type(screen.getByLabelText(/password/i), "nope");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(
      await screen.findByText("Invalid email or password"),
    ).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("opens the MFA prompt when the adapter reports a challenge", async () => {
    mockFetchOnce(200, { success: true, mfaRequired: true });
    render(<Login />);

    await userEvent.type(screen.getByLabelText(/email/i), "a@b.test");
    await userEvent.type(screen.getByLabelText(/password/i), "pw");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(establishSession).not.toHaveBeenCalled();
  });

  it("never logs the submitted password", async () => {
    const logSpy = jest.spyOn(console, "log").mockImplementation(() => {});
    mockFetchOnce(200, SUCCESS_PAYLOAD);
    render(<Login />);

    await userEvent.type(screen.getByLabelText(/email/i), "a@b.test");
    await userEvent.type(screen.getByLabelText(/password/i), "hunter2");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(establishSession).toHaveBeenCalled());
    expect(logSpy.mock.calls.flat().join(" ")).not.toContain("hunter2");
    logSpy.mockRestore();
  });

  it("redirects back to the originally requested route", async () => {
    (useLocation as unknown as jest.Mock).mockReturnValue({
      pathname: "/login",
      state: { from: { pathname: "/audit" } },
    });
    mockFetchOnce(200, SUCCESS_PAYLOAD);
    render(<Login />);

    await userEvent.type(screen.getByLabelText(/email/i), "a@b.test");
    await userEvent.type(screen.getByLabelText(/password/i), "pw");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith("/audit", { replace: true }),
    );
  });
});

describe("useAuthStore.establishSession", () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: true,
    });
  });

  it("stores the token pair and hydrates the user from /auth/me", async () => {
    const api = (await import("../../lib/api")).default;
    const getSpy = jest
      .spyOn(api, "get")
      .mockResolvedValue({ data: { id: 1, email: "a@b.test" } });

    await useAuthStore.getState().establishSession("acc", "ref");

    expect(getSpy).toHaveBeenCalledWith("/auth/me");
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.accessToken).toBe("acc");
    expect(state.user).toEqual({ id: 1, email: "a@b.test" });
    getSpy.mockRestore();
  });

  it("keeps the session authenticated when the profile lookup fails", async () => {
    const api = (await import("../../lib/api")).default;
    const getSpy = jest
      .spyOn(api, "get")
      .mockRejectedValue(new Error("network"));

    await useAuthStore.getState().establishSession("acc", "ref");

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.isLoading).toBe(false);
    expect(state.user).toBeNull();
    getSpy.mockRestore();
  });
});
