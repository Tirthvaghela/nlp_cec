export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validatePassword(pw: string): string | null {
  if (pw.length < 8) return "Use at least 8 characters.";
  if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) return "Include at least one letter and one number.";
  return null;
}
