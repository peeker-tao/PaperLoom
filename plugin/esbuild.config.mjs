import esbuild from "esbuild";

const watch = process.argv.includes("--watch");

/** @type {import('esbuild').BuildOptions} */
const common = {
  bundle: true,
  format: "iife",
  target: ["firefox115"],
  platform: "browser",
  jsx: "automatic",
  sourcemap: false,
  minify: !watch,
  legalComments: "none",
  define: {
    "process.env.NODE_ENV": '"production"',
  },
  logLevel: "info",
};

const builds = [
  {
    ...common,
    entryPoints: ["src/index.ts"],
    outfile: "content/plugin.js",
    globalName: "PaperLoom",
  },
  {
    ...common,
    entryPoints: ["src/prefs.ts"],
    outfile: "content/prefs.js",
    globalName: "PaperLoomPrefs",
  },
];

if (watch) {
  const contexts = await Promise.all(builds.map((options) => esbuild.context(options)));
  await Promise.all(contexts.map((context) => context.watch()));
  console.log("watching…");
} else {
  await Promise.all(builds.map((options) => esbuild.build(options)));
  console.log("plugin bundles built");
}
