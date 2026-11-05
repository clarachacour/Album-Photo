import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { ImagePlus, TriangleAlert } from "lucide-react";
import { PhotoFrameToolbar, PhotoEditToolbar, PhotoPanOverlay } from "@/components/ItemToolbars";
import { DraggableItem } from "@/components/book/DraggableItem";
import { FramedPhoto } from "@/components/book/FramedPhoto";
import { coverItemImageSrc } from "@/lib/api";
import { cropPatch, isCropped, minZoom, pageAspect, wholePhotoFields, zoomToFillTurned } from "@/lib/photoFit";
import { coverPhotoWarnings, isCoverPhotoItem } from "@/lib/printQuality";
import { useNaturalSize } from "@/lib/useNaturalSize";

// A cover image that is a photo: a photo frame, or a template's logo the
// person replaced with their own picture (uploaded: storage_path, no asset).
// Template logos and drawings stay plain images.
export const isCoverPhoto = isCoverPhotoItem;

/**
 * A photo on the front or back cover, edited the same way as a photo inside
 * the album (see AlbumPage): resizing from a side or corner crops it,
 * "Edit" pans, zooms and turns the photo in its frame or turns the frame,
 * "Show whole photo", duplicate, layer order.
 */
export function CoverPhotoItem({
  item,
  orientation,
  // The album's format (A4/A5), for the print resolution warning.
  size,
  editable,
  selected,
  containerRef,
  imageVariant = "medium",
  tid,
  onSelect,
  onUpdate,
  onDuplicate,
  onReorder,
  onDelete,
  onDragStateChange,
}) {
  const { t } = useTranslation();
  // Pan/zoom/rotate mode: local UI state only, like the interior's cropMode.
  const [inCropState, setInCrop] = useState(false);
  const [loadedAspect, setLoadedAspect] = useState(null);
  const isEmpty = !item.image_url;
  const inCrop = inCropState && selected && !isEmpty;
  const rotation = item.rotation || 0;
  const frameRotation = item.frame_rotation || 0;
  const focalX = item.focal_x ?? 0.5;
  const focalY = item.focal_y ?? 0.5;
  const frameAspect = (item.w / item.h) * pageAspect(orientation);
  const photoAspect = item.photo_aspect || loadedAspect;
  // A logo replaced by a photo before it became a photo frame was shown
  // whole in its box: kept that way (and printed that way) until edited.
  const scale = item.scale ?? (item.is_photo ? 1 : minZoom(frameAspect, photoAspect));
  const update = (patch) => onUpdate && onUpdate(patch);
  // Turning the photo in its frame zooms in as needed to keep it filled.
  const turnPhotoPatch = (r) => ({ rotation: r, scale: Math.max(scale, zoomToFillTurned(frameAspect, r)) });
  const withAspect = { ...item, photo_aspect: photoAspect };
  // Print warnings, in the editor only. A photo placed before its pixel size
  // was kept on it is measured from the printed file itself.
  const checkQuality = editable && !!size && !isEmpty && isCoverPhotoItem(item);
  const measured = useNaturalSize(checkQuality && !item.photo_width ? coverItemImageSrc(item, "original") : null);
  const warnings = checkQuality ? coverPhotoWarnings(withAspect, size, orientation, measured) : [];
  // A frame left without a photo is only an editing aid: not printed.
  if (isEmpty && !editable) return null;

  return (
    <>
      <DraggableItem
        item={item}
        // Resizing crops: the photo stays put, the frame's edge moves.
        onChange={(patch) => update(isEmpty ? patch : cropPatch({ ...item, scale }, patch, orientation, photoAspect))}
        edgeHandles
        onSelect={onSelect}
        selected={selected}
        containerRef={containerRef}
        editable={editable && !inCrop}
        tid={tid}
        onDragStateChange={onDragStateChange}
        rotation={inCrop ? rotation : frameRotation}
        onRotate={editable && inCrop ? (r) => update(turnPhotoPatch(r)) : undefined}
        rotateHandleInside
        turnedFrame={!!frameRotation}
        extraStyle={{ transform: frameRotation ? `rotate(${frameRotation}deg)` : undefined }}
      >
        {/* The photo is clipped to its frame; the handles aren't. */}
        <div className="absolute inset-0 overflow-hidden">
          {isEmpty ? (
            <div className="w-full h-full flex flex-col items-center justify-center gap-1 bg-black/5 border-2 border-dashed border-current opacity-60 pointer-events-none">
              <ImagePlus size={18} />
              <span className="text-[9px] uppercase tracking-widest text-center px-1">Add a photo</span>
            </div>
          ) : (
            <FramedPhoto
              src={coverItemImageSrc(item, imageVariant)}
              frameAspect={frameAspect}
              photoAspect={item.photo_aspect}
              zoom={scale}
              focalX={focalX}
              focalY={focalY}
              rotation={rotation}
              onAspect={setLoadedAspect}
            />
          )}
          {warnings.length > 0 && !inCrop && (
            <span
              className="absolute left-1 bottom-1 z-10 inline-flex items-center gap-1 bg-amber-100/95 text-amber-900 border border-amber-300 px-1.5 py-0.5 text-[10px] leading-none rounded-sm"
              title={warnings.map((w) => t(`albumEditor.${w}`)).join("\n")}
              aria-label={warnings.map((w) => t(`albumEditor.${w}`)).join(" ")}
              data-testid={`cover-print-warning-${item.id}`}
            >
              <TriangleAlert size={11} aria-hidden="true" />
              {selected && <span>{warnings.map((w) => t(`albumEditor.${w}Short`)).join(" · ")}</span>}
            </span>
          )}
          {inCrop && <PhotoPanOverlay focalX={focalX} focalY={focalY} onPan={(fx, fy) => update({ focal_x: fx, focal_y: fy })} />}
        </div>
      </DraggableItem>
      {selected && editable && !inCrop && !isEmpty && (
        <PhotoFrameToolbar
          x={item.x}
          y={item.y}
          w={item.w}
          onDuplicate={onDuplicate}
          onEdit={() => setInCrop(true)}
          hideSwap
          hideReorder={!onReorder}
          onBringForward={() => onReorder && onReorder("forward")}
          onSendBackward={() => onReorder && onReorder("backward")}
          // The frame goes, as inside the album (only emptied without onDelete).
          onDelete={onDelete || (() => update({ image_url: null, storage_path: null, asset: null, photo_aspect: null, scale: 1, rotation: 0, frame_rotation: 0, focal_x: 0.5, focal_y: 0.5 }))}
          onShowWhole={isCropped(withAspect, null, orientation) ? () => update(wholePhotoFields(withAspect, null, orientation)) : undefined}
        />
      )}
      {inCrop && (
        <PhotoEditToolbar
          x={item.x}
          y={item.y}
          w={item.w}
          scale={scale}
          minScale={minZoom(frameAspect, photoAspect)}
          onScaleChange={(s) => update({ scale: s })}
          rotation={rotation}
          onRotationChange={(r) => update(turnPhotoPatch(r))}
          frameRotation={frameRotation}
          onFrameRotationChange={(r) => update({ frame_rotation: r })}
          onDone={() => setInCrop(false)}
        />
      )}
    </>
  );
}
