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
                  className="text-blue-600 hover:text-blue-800 text-xs"
                  download
                >
                  下载
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
