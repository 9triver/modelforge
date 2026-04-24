import { useRef, useState, type DragEvent } from 'react';
import type { SearchResult } from '../lib/types';

type Props = {
  onFile: (f: File) => void;
  onDatasetRepo?: (repo: string) => void;
  datasetRepos?: SearchResult[];
  disabled?: boolean;
  hint: string;
};

export default function DatasetUpload({ onFile, onDatasetRepo, datasetRepos, disabled, hint }: Props) {
  const [drag, setDrag] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [selectedRepo, setSelectedRepo] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = (f: File) => {
    setFile(f);
    setSelectedRepo('');
    onFile(f);
  };

  const pickRepo = (repo: string) => {
    setSelectedRepo(repo);
    setFile(null);
    onDatasetRepo?.(repo);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDrag(false);
    if (disabled) return;
    const f = e.dataTransfer.files?.[0];
    if (f) pick(f);
  };

  return (
    <div className="space-y-2">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={handleDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          disabled
            ? 'border-gray-200 bg-gray-50 cursor-not-allowed text-gray-400'
            : drag
            ? 'border-blue-500 bg-blue-50'
            : 'border-gray-300 hover:border-gray-400 bg-white'
        }`}
      >
        <div className="text-3xl mb-2">📄</div>
        {file ? (
          <div>
            <div className="font-medium text-gray-900">{file.name}</div>
            <div className="text-xs text-gray-500 mt-1">
              {(file.size / 1024 / 1024).toFixed(2)} MB
            </div>
          </div>
        ) : selectedRepo ? (
          <div>
            <div className="font-medium text-gray-900">{selectedRepo}</div>
            <div className="text-xs text-gray-500 mt-1">已选择 dataset 仓库</div>
          </div>
        ) : (
          <div>
            <div className="text-sm font-medium">拖拽文件到此，或点击选择</div>
            <div className="text-xs text-gray-500 mt-2">{hint}</div>
          </div>
        )}
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          disabled={disabled}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) pick(f);
          }}
        />
      </div>
      {datasetRepos && datasetRepos.length > 0 && onDatasetRepo && (
        <div className="flex items-center gap-2 text-sm">
          <span className="text-gray-500">或选择已有数据集：</span>
          <select
            value={selectedRepo}
            disabled={disabled}
            onChange={(e) => { if (e.target.value) pickRepo(e.target.value); }}
            className="border border-gray-300 rounded px-2 py-1 text-sm flex-1"
          >
            <option value="">-- 选择 --</option>
            {datasetRepos.map((r) => (
              <option key={r.full_name} value={r.full_name}>
                {r.full_name}{r.data_format ? ` (${r.data_format})` : ''}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
