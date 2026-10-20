/** Fixed names: the local MCP server, the README commands and the token setup refer to them. */
export const NAMES = {
  syncFunction: 'team-docs-sync',
  searchFunction: 'team-docs-search',
  searchCallerRole: 'team-docs-search-caller',
  table: 'team-docs-state',
  schedule: 'team-docs-sync',
  /** SecureString with the Confluence API token that can only read. Put there by hand, never by CDK. */
  tokenParam: '/team-docs/confluence/read-token',
  /** The token's expiry date (YYYY-MM-DD), kept next to it and changed with it. */
  tokenExpiresParam: '/team-docs/confluence/read-token-expires',
} as const;

export const EMBEDDING_MODEL = 'amazon.titan-embed-text-v2:0';
