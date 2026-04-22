const SNIPPETS: Record<string, (repo: string) => string> = {
  'time-series-forecasting': (repo) =>
    `import modelforge\n\nhandler = modelforge.load("${repo}")\npred_df = handler.predict(df)  # DataFrame with timestamp + prediction`,
  'image-classification': (repo) =>
    `import modelforge\nfrom PIL import Image\n\nhandler = modelforge.load("${repo}")\nresults = handler.predict([Image.open("cat.jpg")])\n# [[{"label": "cat", "score": 0.97}, ...]]`,
};

const CLI_SNIPPETS: Record<string, (repo: string) => string> = {
  'time-series-forecasting': (repo) =>
    `modelforge run ${repo} --input data.csv --output pred.csv`,
  'image-classification': (repo) =>
    `modelforge run ${repo} --input images/ --output results.json`,
};

export default function UseModelSnippet({
  fullName,
  task,
}: {
  fullName: string;
  task: string | null;
}) {
  if (!task || !(task in SNIPPETS)) return null;

  return (
    <div className="border border-gray-200 rounded-lg bg-white mb-4 overflow-hidden">
      <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 text-xs font-semibold text-gray-500 uppercase">
        Use this model
      </div>
      <div className="p-4 space-y-3">
        <div>
          <div className="text-xs text-gray-500 mb-1">Python</div>
          <pre className="bg-gray-900 text-gray-100 text-xs p-3 rounded overflow-x-auto">
            {SNIPPETS[task](fullName)}
          </pre>
        </div>
        <div>
          <div className="text-xs text-gray-500 mb-1">CLI</div>
          <pre className="bg-gray-900 text-gray-100 text-xs p-3 rounded overflow-x-auto">
            {CLI_SNIPPETS[task](fullName)}
          </pre>
        </div>
        <div className="text-xs text-gray-500">
          pip install modelforge
        </div>
      </div>
    </div>
  );
}
