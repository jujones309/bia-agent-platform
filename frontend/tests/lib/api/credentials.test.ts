import { describe, expect, it, vi } from "vitest";
import { readPassword, subscribeToPassword, writePassword } from "@/lib/api/credentials";

describe("credentials", () => {
  it("has no session until someone logs in", () => {
    expect(readPassword()).toBeNull();
  });

  it("notifies the gate on login and logout until it unsubscribes", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeToPassword(listener);

    writePassword("secret");
    expect(readPassword()).toBe("secret");
    writePassword(null);
    expect(readPassword()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(2);

    unsubscribe();
    writePassword("again");
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("treats blocked storage as having no session instead of breaking the page", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });

    expect(readPassword()).toBeNull();
  });
});
