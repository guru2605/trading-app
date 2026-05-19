interface Props {
  warnings: string[];
}

export default function ConcentrationBanner({ warnings }: Props) {
  if (warnings.length === 0) return null;

  return (
    <div className="rounded-lg border border-yellow-300 bg-yellow-50 p-4">
      <div className="flex items-start">
        <span className="mr-2 text-yellow-600">&#9888;</span>
        <div>
          <h4 className="text-sm font-medium text-yellow-800">Risk Warnings</h4>
          <ul className="mt-1 space-y-1">
            {warnings.map((w, i) => (
              <li key={i} className="text-sm text-yellow-700">{w}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
