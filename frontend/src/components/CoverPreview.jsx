import React from "react";

// Full cover mockup: no background, uniform size using object-cover
export function CoverMockup({ template, showLabels = false }) {
  const imageSrc = template?.image;
  const templateName = template?.name || "Album";

  return (
    <div className="w-full">
      <div className="w-full aspect-[3/4] overflow-hidden rounded-sm book-shadow">
        {imageSrc ? (
          <img 
            src={imageSrc} 
            alt={templateName} 
            className="w-full h-full object-cover block" 
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gray-100 text-gray-400 text-xs uppercase tracking-widest">
            Image introuvable
          </div>
        )}
      </div>
      {showLabels && (
        <div className="mt-3 text-center text-[10px] tracking-widest uppercase text-[color:var(--muted)]">
          Cover Preview
        </div>
      )}
    </div>
  );
}

// A single front-only cover for smaller previews / dashboards with uniform size
export function CoverFront({ template }) {
  const imageSrc = template?.image;
  const templateName = template?.name || "Album";

  return (
    <div className="relative aspect-[3/4] w-full overflow-hidden book-shadow rounded-sm">
      {imageSrc ? (
        <img 
          src={imageSrc} 
          alt={templateName} 
          className="w-full h-full object-cover block" 
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center bg-gray-100 text-gray-400 text-xs uppercase tracking-widest">
          No image
        </div>
      )}
    </div>
  );
}