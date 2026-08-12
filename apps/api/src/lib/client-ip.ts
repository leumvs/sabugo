export function clientIp(headerValue: string | undefined): string | undefined {
  const first = headerValue?.split(",")[0]?.trim();
  return first ? first : undefined;
}
