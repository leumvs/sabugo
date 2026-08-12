/** The closed list of error codes, and the only definition of it. */
export const ERROR_STATUS = {
  INVALID_PARAMS: 400,
  INVALID_IMAGE: 400,
  NOT_FOUND: 404,
  UNSUPPORTED_FORMAT: 415,
  IMAGE_TOO_LARGE: 413,
  NO_ROOTS_DETECTED: 422,
  RATE_LIMITED: 429,
  SERVICE_AT_CAPACITY: 503,
  PROCESSING_TIMEOUT: 500,
  INTERNAL_ERROR: 500,
} as const;

export type ErrorCode = keyof typeof ERROR_STATUS;

export type ErrorEnvelope = {
  code: ErrorCode;
  message: string;
  details?: Record<string, unknown>;
};

export function isErrorCode(value: string): value is ErrorCode {
  return value in ERROR_STATUS;
}

/** `message` is derived and never written by hand: two spellings drift. */
export function envelope(code: ErrorCode, details?: Record<string, unknown>): ErrorEnvelope {
  return details
    ? { code, message: code.toLowerCase(), details }
    : { code, message: code.toLowerCase() };
}

/** The same envelope reaches the client over HTTP and over SSE. */
export class ApiError extends Error {
  constructor(
    readonly code: ErrorCode,
    readonly details?: Record<string, unknown>,
  ) {
    super(code);
  }

  get status(): number {
    return ERROR_STATUS[this.code];
  }

  get envelope(): ErrorEnvelope {
    return envelope(this.code, this.details);
  }
}
