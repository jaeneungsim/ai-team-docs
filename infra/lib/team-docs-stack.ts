import { CfnOutput, Duration, RemovalPolicy, Stack, StackProps } from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as scheduler from 'aws-cdk-lib/aws-scheduler';
import { Construct } from 'constructs';
import { EMBEDDING_MODEL, NAMES } from './names';
import { pythonCode } from './python-code';

export interface TeamDocsProps extends StackProps {
  /** The Confluence site's cloud id. Kept in cdk.context.json, which is not committed. */
  readonly confluenceCloudId: string;
  /** The Atlassian account email that goes with the read token in Basic auth. Not committed either. */
  readonly confluenceEmail: string;
  readonly spaceKey: string;
  /** IAM Identity Center permission set whose role may assume the search caller role, e.g. AdministratorAccess. */
  readonly searchCallerPermissionSet: string;
  /** Titan input tokens per calendar month. Above this, changed pages are indexed for keywords only. */
  readonly embedMonthlyTokens: number;
  /** Tests skip bundling; deploys bundle the Python code with its dependencies. */
  readonly code?: lambda.Code;
}

/**
 * A read-only sync from one Confluence space into a search index, the search function, and the
 * one role the local MCP server uses to call it. There is no public endpoint.
 */
export class TeamDocsStack extends Stack {
  constructor(scope: Construct, id: string, props: TeamDocsProps) {
    super(scope, id, props);
    const { account, region, partition } = this;
    const param = (name: string) => `arn:${partition}:ssm:${region}:${account}:parameter${name}`;

    const table = new dynamodb.Table(this, 'State', {
      tableName: NAMES.table,
      partitionKey: { name: 'pk', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'sk', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'expires_at',
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // Raw pages, converted pages, chunks, vectors and index builds. The sync tags files nothing uses
    // any more "superseded" (a page's old version, a removed page, a replaced index build), and the
    // lifecycle rule deletes a tagged file once it is a week old. The sync may not delete objects.
    const bucket = new s3.Bucket(this, 'Docs', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      lifecycleRules: [{ id: 'superseded-files', tagFilters: { superseded: 'true' }, expiration: Duration.days(7) }],
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    const code = props.code ?? pythonCode();
    const fn = (id: string, name: string, handler: string, timeout: Duration, environment: Record<string, string>) =>
      new lambda.Function(this, id, {
        functionName: name,
        code,
        handler: `team_docs.handlers.${handler}`,
        runtime: lambda.Runtime.PYTHON_3_13,
        architecture: lambda.Architecture.ARM_64,
        memorySize: 512,
        timeout,
        environment: { TABLE_NAME: table.tableName, BUCKET_NAME: bucket.bucketName, ...environment },
        loggingFormat: lambda.LoggingFormat.JSON,
        logGroup: new logs.LogGroup(this, `${id}Logs`, {
          retention: logs.RetentionDays.TWO_WEEKS,
          removalPolicy: RemovalPolicy.DESTROY,
        }),
      });

    const sync = fn('Sync', NAMES.syncFunction, 'sync', Duration.minutes(5), {
      CONFLUENCE_CLOUD_ID: props.confluenceCloudId,
      CONFLUENCE_EMAIL: props.confluenceEmail,
      SPACE_KEY: props.spaceKey,
      TOKEN_PARAM: NAMES.tokenParam,
      TOKEN_EXPIRES_PARAM: NAMES.tokenExpiresParam,
      EMBED_MONTHLY_TOKENS: String(props.embedMonthlyTokens),
    });
    const search = fn('Search', NAMES.searchFunction, 'search', Duration.seconds(30), {});

    const embeddingModel = new iam.PolicyStatement({
      sid: 'OnlyTheEmbeddingModel',
      actions: ['bedrock:InvokeModel'],
      resources: [`arn:${partition}:bedrock:${region}::foundation-model/${EMBEDDING_MODEL}`],
    });

    // The sync reads the token, reads and writes its table and bucket, and never deletes an object.
    sync.addToRolePolicy(new iam.PolicyStatement({
      sid: 'ReadTheConfluenceToken',
      actions: ['ssm:GetParameter'],
      resources: [param(NAMES.tokenParam), param(NAMES.tokenExpiresParam)],
    }));
    sync.addToRolePolicy(embeddingModel);
    table.grantReadWriteData(sync);
    bucket.grantRead(sync);
    bucket.grantPut(sync);

    // The search reads the index files and the STATE item, and nothing else.
    search.addToRolePolicy(embeddingModel);
    bucket.grantRead(search, 'index/*');
    search.addToRolePolicy(new iam.PolicyStatement({
      sid: 'OnlyTheStateItem',
      actions: ['dynamodb:GetItem'],
      resources: [table.tableArn],
      conditions: { 'ForAllValues:StringEquals': { 'dynamodb:LeadingKeys': ['STATE'] } },
    }));

    const schedulerRole = new iam.Role(this, 'SchedulerRole', {
      assumedBy: new iam.ServicePrincipal('scheduler.amazonaws.com', {
        conditions: { StringEquals: { 'aws:SourceAccount': account } },
      }),
    });
    sync.grantInvoke(schedulerRole);
    new scheduler.CfnSchedule(this, 'SyncSchedule', {
      name: NAMES.schedule,
      description: 'Sync the Confluence space into the search index',
      scheduleExpression: 'rate(10 minutes)',
      flexibleTimeWindow: { mode: 'OFF' },
      // No retries: a failed run is simply the next run, ten minutes later.
      target: { arn: sync.functionArn, roleArn: schedulerRole.roleArn, retryPolicy: { maximumRetryAttempts: 0 } },
    });

    // The local MCP server switches from the developer's SSO login to this role, which can invoke
    // the search function and nothing else.
    const ssoRoles = `arn:${partition}:iam::${account}:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_${props.searchCallerPermissionSet}_*`;
    const caller = new iam.Role(this, 'SearchCaller', {
      roleName: NAMES.searchCallerRole,
      description: 'Used by the local MCP server: can invoke the team docs search function and nothing else',
      assumedBy: new iam.AccountPrincipal(account).withConditions({ ArnLike: { 'aws:PrincipalArn': ssoRoles } }),
      maxSessionDuration: Duration.hours(1),
    });
    search.grantInvoke(caller);

    new CfnOutput(this, 'SearchFunctionName', { value: search.functionName });
    new CfnOutput(this, 'SyncFunctionName', { value: sync.functionName });
    new CfnOutput(this, 'SearchCallerRoleArn', { value: caller.roleArn, description: 'role_arn of the team-docs-search AWS profile' });
    new CfnOutput(this, 'BucketName', { value: bucket.bucketName });
    new CfnOutput(this, 'TableName', { value: table.tableName });
  }
}
