import { App } from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { TeamDocsStack } from '../lib/team-docs-stack';

const template = Template.fromStack(
  new TeamDocsStack(new App(), 'TeamDocs', {
    env: { account: '111111111111', region: 'ap-southeast-2' },
    confluenceCloudId: 'cloud-id',
    confluenceEmail: 'someone@example.com',
    spaceKey: 'INV',
    searchCallerPermissionSet: 'AdministratorAccess',
    embedMonthlyTokens: 2_000_000,
    code: lambda.Code.fromInline('def handler(event, context):\n    return None\n'),
  }),
);

type Statement = { Sid?: string; Action: string | string[]; Resource?: unknown; Condition?: unknown };

/** Every statement in the policies attached to the role whose logical id starts with `prefix`. */
function statementsOf(prefix: string): Statement[] {
  const roleIds = Object.keys(template.findResources('AWS::IAM::Role')).filter((id) => id.startsWith(prefix));
  return Object.values(template.findResources('AWS::IAM::Policy'))
    .filter((policy) => (policy.Properties.Roles as { Ref: string }[]).some((role) => roleIds.includes(role.Ref)))
    .flatMap((policy) => policy.Properties.PolicyDocument.Statement as Statement[]);
}

const actionsOf = (statements: Statement[]) => statements.flatMap((s) => (Array.isArray(s.Action) ? s.Action : [s.Action]));

test('there is no public endpoint', () => {
  for (const type of ['AWS::Lambda::Url', 'AWS::ApiGateway::RestApi', 'AWS::ApiGatewayV2::Api']) {
    template.resourceCountIs(type, 0);
  }
});

test('the search caller role trusts only the SSO role and can only invoke the search function', () => {
  const roles = template.findResources('AWS::IAM::Role', { Properties: { RoleName: 'team-docs-search-caller' } });
  const [role] = Object.values(roles);
  expect(role.Properties.MaxSessionDuration).toBe(3600);
  const trust = role.Properties.AssumeRolePolicyDocument.Statement;
  expect(trust).toHaveLength(1);
  expect(JSON.stringify(trust[0].Condition.ArnLike['aws:PrincipalArn'])).toContain(
    ':iam::111111111111:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_AdministratorAccess_*',
  );
  expect(new Set(actionsOf(statementsOf('SearchCaller')))).toEqual(new Set(['lambda:InvokeFunction']));
});

test('the search function reads the index and the STATE item, and calls only Titan', () => {
  const statements = statementsOf('SearchServiceRole');
  const actions = actionsOf(statements);
  expect(actions).not.toContain('ssm:GetParameter');
  expect(actions.filter((a) => a.startsWith('dynamodb:'))).toEqual(['dynamodb:GetItem']);
  expect(actions.some((a) => /^s3:(Put|Delete)/.test(a))).toBe(false);
  const state = statements.find((s) => s.Sid === 'OnlyTheStateItem');
  expect(state?.Condition).toEqual({ 'ForAllValues:StringEquals': { 'dynamodb:LeadingKeys': ['STATE'] } });
  const model = statements.find((s) => s.Sid === 'OnlyTheEmbeddingModel');
  expect(JSON.stringify(model?.Resource)).toContain('foundation-model/amazon.titan-embed-text-v2:0');
});

test('the sync reads only the token parameters and never deletes objects', () => {
  const statements = statementsOf('SyncServiceRole');
  const token = statements.find((s) => s.Sid === 'ReadTheConfluenceToken');
  expect(token?.Action).toBe('ssm:GetParameter');
  expect(JSON.stringify(token?.Resource)).toContain('parameter/team-docs/confluence/read-token');
  expect(actionsOf(statements).some((a) => a.startsWith('s3:Delete'))).toBe(false);
});

test('the sync runs every 10 minutes without retries', () => {
  template.hasResourceProperties('AWS::Scheduler::Schedule', {
    ScheduleExpression: 'rate(10 minutes)',
    Target: Match.objectLike({ RetryPolicy: { MaximumRetryAttempts: 0 } }),
  });
  template.hasResourceProperties('AWS::Lambda::Function', {
    FunctionName: 'team-docs-sync',
    Timeout: 300,
    Runtime: 'python3.13',
    Architectures: ['arm64'],
  });
});

test('superseded files expire anywhere in the bucket, and logs are kept for two weeks', () => {
  template.hasResourceProperties('AWS::S3::Bucket', {
    LifecycleConfiguration: {
      Rules: [
        Match.objectLike({
          Prefix: Match.absent(),
          TagFilters: [{ Key: 'superseded', Value: 'true' }],
          ExpirationInDays: 7,
        }),
      ],
    },
  });
  template.allResourcesProperties('AWS::Logs::LogGroup', { RetentionInDays: 14 });
});
