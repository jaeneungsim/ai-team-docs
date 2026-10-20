#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { TeamDocsStack } from '../lib/team-docs-stack';

const app = new cdk.App();
// Site- and account-specific values live in cdk.context.json, which is not committed.
const required = (key: string): string => {
  const value = app.node.tryGetContext(key);
  if (!value) throw new Error(`Set "${key}" in infra/cdk.context.json (see README).`);
  return String(value);
};

new TeamDocsStack(app, 'TeamDocs', {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: 'ap-southeast-2' },
  stackName: 'team-docs',
  description: 'Up-to-date team docs for AI agents: read-only Confluence sync, hybrid search, local MCP tool',
  confluenceCloudId: required('confluenceCloudId'),
  confluenceEmail: required('confluenceEmail'),
  spaceKey: app.node.tryGetContext('spaceKey') ?? 'INV',
  searchCallerPermissionSet: required('searchCallerPermissionSet'),
  embedMonthlyTokens: Number(app.node.tryGetContext('embedMonthlyTokens') ?? 2_000_000),
});

cdk.Tags.of(app).add('project', 'ai-team-docs');
