import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cpSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { AssetHashType } from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';

const ROOT = resolve(__dirname, '..', '..');
const SOURCES = ['src/team_docs', 'requirements.txt'];
const SKIP = (path: string) => path.includes('__pycache__') || path.endsWith('.pyc');

function files(path: string): string[] {
  if (statSync(path).isFile()) return [path];
  return readdirSync(path).flatMap((name) => files(join(path, name)));
}

/** Hash only what goes into the bundle, so unrelated changes do not rebuild it. */
function sourceHash(): string {
  const hash = createHash('sha256');
  for (const file of SOURCES.flatMap((s) => files(join(ROOT, s))).filter((f) => !SKIP(f)).sort()) {
    hash.update(relative(ROOT, file)).update(readFileSync(file));
  }
  return hash.digest('hex');
}

/**
 * One code bundle for both functions: the team_docs package and the pinned dependencies built
 * for Linux arm64. Bundles locally with uv; falls back to Docker.
 */
export function pythonCode(): lambda.Code {
  return lambda.Code.fromAsset(ROOT, {
    assetHashType: AssetHashType.CUSTOM,
    assetHash: sourceHash(),
    exclude: ['*', '!src', '!src/team_docs', '!src/team_docs/**', '!requirements.txt', '**/__pycache__'],
    bundling: {
      image: lambda.Runtime.PYTHON_3_13.bundlingImage,
      platform: 'linux/arm64',
      command: [
        'bash', '-c',
        'pip install --no-cache-dir -r requirements.txt -t /asset-output && cp -r src/team_docs /asset-output/team_docs',
      ],
      local: {
        tryBundle(outputDir: string): boolean {
          try {
            execFileSync('uv', [
              'pip', 'install', '--quiet', '--target', outputDir,
              '--python-platform', 'aarch64-manylinux_2_28', '--python-version', '3.13',
              '--only-binary', ':all:', '-r', join(ROOT, 'requirements.txt'),
            ], { stdio: 'inherit' });
            cpSync(join(ROOT, 'src', 'team_docs'), join(outputDir, 'team_docs'), { recursive: true, filter: (p) => !SKIP(p) });
            return true;
          } catch (err) {
            process.stderr.write(`local bundling failed, trying Docker: ${err}\n`);
            return false;
          }
        },
      },
    },
  });
}
