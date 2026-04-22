import type { FileItem } from '../lib/types';

export default function FileList({
  files,
  namespace,
  name,
  revision = 'main',
}: {
  files: FileItem[];
  namespace: string;
  name: string;
  revision?: string;
}) {
  if (files.length === 0) return <div className="text-gray-500 py-4">（暂无文件）</div>;

  const downloadUrl = (path: string) =>
    `/api/v1/repos/${namespace}/${name}/raw/${path}?revision=${encodeURIComponent(revision)}`;

  return (
    <div className="border border-gray-200 rounded overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-3 py-2 text-left font-semibold text-gray-700">路径</th>
            <th className="px-3 py-2 text-right font-semibold text-gray-700 w-24">大小</th>
            <th className="px-3 py-2 text-center font-semibold text-gray-700 w-16">LFS</th>
            <th className="px-3 py-2 text-center font-semibold text-gray-700 w-16"></th>
          </tr>
        </thead>
        <tbody>
          {files.map((f) => (
            <tr key={f.path} className="border-t border-gray-200 hover:bg-gray-50">
              <td className="px-3 py-2 font-mono text-gray-800">{f.path}</td>
              <td className="px-3 py-2 text-right text-gray-600">{f.size_human}</td>
              <td className="px-3 py-2 text-center">
                {f.is_lfs && <span className="text-xs px-1.5 py-0.5 bg-amber-100 text-amber-800 rounded">LFS</span>}
              </td>
              <td className="px-3 py-2 text-center">
                <a
                  href={downloadUrl(f.path)}
                  className="text-gray-400 hover:text-blue-600 inline-block"
                  download
                  title="下载"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                    <path d="M10.75 2.75a.75.75 0 00-1.5 0v8.614L6.295 8.235a.75.75 0 10-1.09 1.03l4.25 4.5a.75.75 0 001.09 0l4.25-4.5a.75.75 0 00-1.09-1.03l-2.955 3.129V2.75z" />
                    <path d="M3.5 12.75a.75.75 0 00-1.5 0v2.5A2.75 2.75 0 004.75 18h10.5A2.75 2.75 0 0018 15.25v-2.5a.75.75 0 00-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5z" />
                  </svg>
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
