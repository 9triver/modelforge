import { useEffect, useState } from 'react';
import { getCocoPreview, getCsvPreview, getImagePreview } from '../lib/api';
import type { CocoPreview, CsvPreview, FileItem, ImagePreview } from '../lib/types';

type Props = {
  namespace: string;
  name: string;
  revision: string;
  dataFormat: string | null;
  files: FileItem[];
};

export default function DataPreviewTab({ namespace, name, revision, dataFormat, files }: Props) {
  if (dataFormat === 'coco_json') {
    return <CocoJsonPreview namespace={namespace} name={name} revision={revision} />;
  }
  if (dataFormat === 'image_folder') {
    return <ImageFolderPreview namespace={namespace} name={name} revision={revision} />;
  }
  if (dataFormat === 'csv' || dataFormat === 'parquet') {
    const csvFile = files.find((f) => f.path.endsWith('.csv') || f.path.endsWith('.tsv'));
    if (!csvFile) {
      return <div className="text-sm text-gray-500">未找到 CSV 文件</div>;
    }
    return <CsvTablePreview namespace={namespace} name={name} revision={revision} path={csvFile.path} />;
  }
  return (
    <div className="text-sm text-gray-500">
      未知数据格式 <code className="bg-gray-100 px-1 rounded">{dataFormat || '(未指定)'}</code>，无法预览。
    </div>
  );
}

function CsvTablePreview({ namespace, name, revision, path }: {
  namespace: string; name: string; revision: string; path: string;
}) {
  const [data, setData] = useState<CsvPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getCsvPreview(namespace, name, path, revision)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [namespace, name, revision, path]);

  if (loading) return <div className="text-sm text-gray-500">加载中...</div>;
  if (error) return <div className="bg-red-50 text-red-800 p-3 rounded text-sm">{error}</div>;
  if (!data) return null;

  return (
    <div className="space-y-2">
      <div className="text-sm text-gray-500">
        {path} · 显示前 {data.rows.length} / {data.total_rows} 行
      </div>
      <div className="overflow-x-auto border border-gray-200 rounded">
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              {data.columns.map((col, i) => (
                <th key={i} className="px-3 py-2 text-left text-xs text-gray-600 font-medium whitespace-nowrap">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, ri) => (
              <tr key={ri} className="border-t border-gray-100 hover:bg-gray-50">
                {row.map((cell, ci) => (
                  <td key={ci} className="px-3 py-1.5 whitespace-nowrap font-mono text-xs">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ImageFolderPreview({ namespace, name, revision }: {
  namespace: string; name: string; revision: string;
}) {
  const [data, setData] = useState<ImagePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getImagePreview(namespace, name, revision)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [namespace, name, revision]);

  if (loading) return <div className="text-sm text-gray-500">加载中...</div>;
  if (error) return <div className="bg-red-50 text-red-800 p-3 rounded text-sm">{error}</div>;
  if (!data) return null;

  return (
    <div className="space-y-4">
      {data.classes.map((cls) => (
        <div key={cls.name}>
          <div className="text-sm font-medium text-gray-700 mb-2">
            {cls.name} <span className="text-gray-400 font-normal">({cls.count} 张)</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {cls.samples.map((s) => (
              <div key={s.path} className="w-32 h-32 rounded border border-gray-200 overflow-hidden" title={s.path}>
                <img
                  src={`data:image/jpeg;base64,${s.thumbnail_b64}`}
                  alt={s.path}
                  className="w-full h-full object-cover"
                />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function CocoJsonPreview({ namespace, name, revision }: {
  namespace: string; name: string; revision: string;
}) {
  const [data, setData] = useState<CocoPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getCocoPreview(namespace, name, revision)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [namespace, name, revision]);

  if (loading) return <div className="text-sm text-gray-500">加载中...</div>;
  if (error) return <div className="bg-red-50 text-red-800 p-3 rounded text-sm">{error}</div>;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="text-sm text-gray-600">
        {data.total_images} 张图片 · {data.total_annotations} 个标注 · {data.categories.length} 个类别
      </div>

      <div className="flex flex-wrap gap-2">
        {data.categories.map((c) => (
          <span key={c.name} className="text-xs px-2 py-1 bg-gray-100 rounded">
            {c.name} <span className="text-gray-400">({c.count})</span>
          </span>
        ))}
      </div>

      <div className="flex flex-wrap gap-3">
        {data.samples.map((s) => (
          <div key={s.path} className="rounded border border-gray-200 overflow-hidden" title={`${s.path} (${s.n_annotations} annotations)`}>
            <img
              src={`data:image/jpeg;base64,${s.thumbnail_b64}`}
              alt={s.path}
              className="w-64 h-auto"
            />
            <div className="text-xs text-gray-500 px-2 py-1 bg-gray-50">
              {s.n_annotations} annotations
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
