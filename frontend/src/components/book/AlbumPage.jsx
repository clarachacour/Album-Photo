import React, { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { photoImageUrl } from "@/lib/api";
import { PhotoFrameToolbar, PhotoEditToolbar, PhotoPanOverlay, TextItemToolbar } from "@/components/ItemToolbars";
import LayoutPicker from "@/components/LayoutPicker";
import { ImagePlus, LayoutGrid, Type, Trash2 } from "lucide-react";
import { CenterGuides } from "@/components/book/CenterGuides";
import { DraggableItem } from "@/components/book/DraggableItem";
import { useConfirm } from "@/components/ConfirmDialog";
import { REFERENCE_PAGE_PX } from "@/components/book/textMeasure";

/**
 * AlbumPage renders one printable page with draggable + resizable items.
 */
export function AlbumPage({
  page,
  orientation = "portrait",
  pageIndex = 0,
  highRes = false,
  editable = false,
  onSelectItem,
  onUpdateItem,
  onDeleteItem,
  swapSourceItemId,
  onSwapAction,
  onAddPhotoAt,
  onReplacePhoto,
  onReorderLayer,
  onApplyLayout,
  onDeletePage,
  placingPhotoId,
  onPhotoPlaced,
  selectedItemId,
  cropMode = false,
  onEnterCrop,
  onExitCrop,
  placingText = false,
  onPlaceText,
  onStartAddText,
  autoEditItemId,
  onTextEditHandled,
}) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const containerRef = useRef(null);
  const aspect = orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]";
  const items = page?.items || [];
  const [draggingId, setDraggingId] = useState(null);
  const [textEditId, setTextEditId] = useState(null);
  const [showLayoutPicker, setShowLayoutPicker] = useState(false);
  const itemsRef = useRef(items);
  itemsRef.current = items;

  React.useEffect(() => {
    if (autoEditItemId && items.some((it) => it.id === autoEditItemId)) {
      setTextEditId(autoEditItemId);
      onTextEditHandled && onTextEditHandled();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoEditItemId]);

  const handlePhotoDragStateChange = (item, isDragging) => {
    setDraggingId(isDragging ? item.id : null);
  };

  const handleDragOver = (e) => {
    if (!editable) return;
    e.preventDefault();
  };

  const handleDrop = (e) => {
    if (!editable) return;
    e.preventDefault();
    const photoId = e.dataTransfer.getData("text/photo-id");
    if (!photoId || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const nx = (e.clientX - rect.left) / rect.width;
    const ny = (e.clientY - rect.top) / rect.height;
    // Dropped onto an existing photo frame → replace its content.
    const target = items.find((it) => it.type === "photo" && nx >= it.x && nx <= it.x + it.w && ny >= it.y && ny <= it.y + it.h);
    if (target) {
      onReplacePhoto && onReplacePhoto(target.id, photoId);
    } else {
      // Dropped on empty space → create a new frame centered on the drop point.
      const w = 0.35, h = 0.3;
      onAddPhotoAt && onAddPhotoAt(photoId, {
        x: Math.min(Math.max(nx - w / 2, 0), 1 - w),
        y: Math.min(Math.max(ny - h / 2, 0), 1 - h),
        w,
        h,
      });
    }
  };

  const handleClick = (e) => {
    if (swapSourceItemId) {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const nx = (e.clientX - rect.left) / rect.width;
      const ny = (e.clientY - rect.top) / rect.height;
      const target = itemsRef.current.find(
        (it) => it.type === "photo" && it.id !== swapSourceItemId && nx >= it.x && nx <= it.x + it.w && ny >= it.y && ny <= it.y + it.h
      );
      onSwapAction && onSwapAction(pageIndex, target ? target.id : null);
      return;
    }
    if (placingPhotoId) {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const nx = (e.clientX - rect.left) / rect.width;
      const ny = (e.clientY - rect.top) / rect.height;
      const target = itemsRef.current.find(
        (it) => it.type === "photo" && nx >= it.x && nx <= it.x + it.w && ny >= it.y && ny <= it.y + it.h
      );
      if (target) {
        onReplacePhoto && onReplacePhoto(target.id, placingPhotoId);
      } else {
        const w = 0.35, h = 0.3;
        onAddPhotoAt && onAddPhotoAt(placingPhotoId, {
          x: Math.min(Math.max(nx - w / 2, 0), 1 - w),
          y: Math.min(Math.max(ny - h / 2, 0), 1 - h),
          w,
          h,
        });
      }
      onPhotoPlaced && onPhotoPlaced();
      return;
    }
    if (e.target !== e.currentTarget) return; // ignore clicks that landed on an existing item
    if (placingText) {
      const rect = containerRef.current.getBoundingClientRect();
      const nx = (e.clientX - rect.left) / rect.width;
      const ny = (e.clientY - rect.top) / rect.height;
      onPlaceText && onPlaceText({ x: Math.min(Math.max(nx - 0.25, 0), 0.7), y: Math.min(Math.max(ny - 0.04, 0), 0.92) });
    } else {
      onSelectItem && onSelectItem(null);
    }
  };

  return (
    <div
      ref={containerRef}
      className={`relative w-full ${aspect} bg-[color:var(--paper)] ${placingText ? "cursor-text" : ""} ${placingPhotoId ? "cursor-copy" : ""}`}
      style={{ containerType: "inline-size" }}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      onClick={handleClick}
    >
      <div className="absolute inset-0 grain pointer-events-none" />
      {items.map((item) => {
        const isSel = selectedItemId === item.id;
        if (item.type === "photo") {
          const scale = Math.max(item.scale || 1, 1);
          const focalX = item.focal_x ?? 0.5;
          const focalY = item.focal_y ?? 0.5;
          const rotation = item.rotation || 0;
          const inCrop = isSel && cropMode;
          const isSwapSource = swapSourceItemId === item.id;
          const isEmpty = !item.photo_id;
          return (
            <React.Fragment key={item.id}>
              <DraggableItem
                item={item}
                onChange={(patch) => onUpdateItem && onUpdateItem(item.id, patch)}
                onSelect={() => onSelectItem && onSelectItem(item)}
                onDoubleClick={() => editable && !isEmpty && onSwapAction && onSwapAction(pageIndex, item.id)}
                selected={isSel}
                containerRef={containerRef}
                editable={editable && !inCrop}
                tid={`page-photo-${item.id}`}
                onDragStateChange={(d, mode) => handlePhotoDragStateChange(item, d, mode)}
                extraStyle={{ overflow: "hidden", outline: isSwapSource ? "2px dashed var(--coral)" : undefined, outlineOffset: isSwapSource ? "-2px" : undefined }}
              >
                {isEmpty ? (
                  <div className="w-full h-full flex flex-col items-center justify-center gap-2 bg-[color:var(--editor-canvas)] border-2 border-dashed border-[color:var(--ink)]/20 pointer-events-none">
                    <ImagePlus size={22} className="text-[color:var(--muted)]" />
                    <span className="text-[10px] text-[color:var(--muted)] uppercase tracking-widest text-center px-2">Drop a photo here</span>
                  </div>
                ) : (
                  <img
                    src={photoImageUrl(item.photo_id, highRes ? "print" : "medium")}
                    alt=""
                    className="w-full h-full pointer-events-none select-none"
                    style={{
                      objectFit: "cover",
                      transform: `scale(${scale}) rotate(${rotation}deg)`,
                      transformOrigin: `${focalX * 100}% ${focalY * 100}%`,
                      objectPosition: `${focalX * 100}% ${focalY * 100}%`,
                    }}
                    draggable={false}
                  />
                )}
                {inCrop && !isEmpty && (
                  <PhotoPanOverlay
                    focalX={focalX}
                    focalY={focalY}
                    onPan={(fx, fy) => onUpdateItem && onUpdateItem(item.id, { focal_x: fx, focal_y: fy })}
                  />
                )}
              </DraggableItem>
              {isSel && editable && !inCrop && !isEmpty && (
                <PhotoFrameToolbar
                  x={item.x}
                  y={item.y}
                  w={item.w}
                  onEdit={() => onEnterCrop && onEnterCrop(item.id)}
                  onSwap={() => onSwapAction && onSwapAction(pageIndex, isSwapSource ? null : item.id)}
                  isSwapping={isSwapSource}
                  onBringForward={() => onReorderLayer && onReorderLayer(item.id, "forward")}
                  onSendBackward={() => onReorderLayer && onReorderLayer(item.id, "backward")}
                  onDelete={() => onDeleteItem && onDeleteItem(item.id)}
                />
              )}
              {isSel && editable && isEmpty && (
                <PhotoFrameToolbar
                  x={item.x}
                  y={item.y}
                  w={item.w}
                  onEdit={() => {}}
                  onSwap={() => {}}
                  isSwapping={false}
                  onBringForward={() => onReorderLayer && onReorderLayer(item.id, "forward")}
                  onSendBackward={() => onReorderLayer && onReorderLayer(item.id, "backward")}
                  onDelete={() => onDeleteItem && onDeleteItem(item.id)}
                  emptyFrame
                />
              )}
              {inCrop && !isEmpty && (
                <PhotoEditToolbar
                  x={item.x}
                  y={item.y}
                  w={item.w}
                  scale={scale}
                  onScaleChange={(s) => onUpdateItem && onUpdateItem(item.id, { scale: s })}
                  rotation={rotation}
                  onRotationChange={(r) => onUpdateItem && onUpdateItem(item.id, { rotation: r })}
                  onDone={() => onExitCrop && onExitCrop()}
                />
              )}
            </React.Fragment>
          );
        }
        if (item.type === "text") {
          const inTextEdit = isSel && textEditId === item.id;
          return (
            <React.Fragment key={item.id}>
              <DraggableItem
                item={item}
                onChange={(patch) => onUpdateItem && onUpdateItem(item.id, patch)}
                onSelect={() => onSelectItem && onSelectItem(item)}
                onDoubleClick={() => setTextEditId(item.id)}
                selected={isSel}
                containerRef={containerRef}
                editable={editable && !inTextEdit}
                tid={`page-text-${item.id}`}
                onDragStateChange={(d) => setDraggingId(d ? item.id : null)}
                extraStyle={{
                  color: item.color || "#1A1A17",
                  fontFamily: item.font || "Cormorant Garamond, serif",
                  // Was a flat `${item.font_size}px` — a fixed pixel size
                  // with no relationship to how wide the page is actually
                  // being rendered. The live editor and the print export
                  // render this same page at very different physical
                  // pixel widths (the editor fits the book to the
                  // viewport; the print export renders at full print
                  // resolution), so a fixed px size looked completely
                  // different — wrong size, and consequently wrong-looking
                  // position once the text wrapped differently — between
                  // the two. cqw (relative to the page's own container
                  // width, see containerType on this component's root
                  // div) is what the cover text and AutoFitText already
                  // use for exactly this reason; this makes plain page
                  // text consistent with them instead of being the one
                  // text type still sized in absolute pixels.
                  fontSize: `${(((item.font_size || 16) / REFERENCE_PAGE_PX) * 100).toFixed(2)}cqw`,
                  fontWeight: item.font_weight || "normal",
                  fontStyle: item.font_style || "normal",
                  lineHeight: 1.15,
                  overflow: "hidden",
                  wordBreak: "break-word",
                  padding: "2px 0",
                  textAlign: item.text_align || "left",
                }}
              >
                {inTextEdit ? (
                  <textarea
                    autoFocus
                    value={item.content}
                    onChange={(e) => onUpdateItem && onUpdateItem(item.id, { content: e.target.value })}
                    onFocus={(e) => e.target.select()}
                    onPointerDown={(e) => e.stopPropagation()}
                    onBlur={() => setTextEditId(null)}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") { e.currentTarget.blur(); }
                      e.stopPropagation();
                    }}
                    className="whitespace-pre-wrap block w-full h-full bg-transparent border-0 outline-none resize-none"
                    style={{ color: "inherit", font: "inherit", lineHeight: "inherit" }}
                    data-testid={`page-text-input-${item.id}`}
                  />
                ) : (
                  <span className="whitespace-pre-wrap block w-full h-full pointer-events-none select-none">
                    {item.content}
                  </span>
                )}
              </DraggableItem>
              {isSel && editable && (
                <TextItemToolbar
                  x={item.x}
                  y={item.y}
                  w={item.w}
                  item={item}
                  onChange={(patch) => onUpdateItem && onUpdateItem(item.id, patch)}
                  onDelete={() => onDeleteItem && onDeleteItem(item.id)}
                />
              )}
            </React.Fragment>
          );
        }
        return null;
      })}
      <CenterGuides
        show={editable && !!draggingId}
        guideX={page?.align_guide_x}
        guideY={page?.align_guide_y}
      />
      {editable && (onApplyLayout || onStartAddText || onDeletePage) && (
        <div className={`absolute top-1/2 -translate-y-1/2 ${pageIndex % 2 === 0 ? "-right-9" : "-left-9"} z-30 flex flex-col gap-2`}>
          {onApplyLayout && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowLayoutPicker(true);
              }}
              data-testid={`page-layout-btn-${pageIndex}`}
              className="flex flex-col items-center gap-1 bg-[color:var(--coral)] text-[color:var(--paper)] px-1.5 py-2 hover:brightness-110 transition-all shadow-md"
              title={t("albumPage.changeLayout")}
            >
              <LayoutGrid size={13} />
            </button>
          )}
          {onStartAddText && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onStartAddText();
              }}
              data-testid={`page-add-text-btn-${pageIndex}`}
              className="flex flex-col items-center gap-1 bg-[color:var(--coral)] text-[color:var(--paper)] px-1.5 py-2 hover:brightness-110 transition-all shadow-md"
              title={t("albumPage.addTextBox")}
            >
              <Type size={13} />
            </button>
          )}
          {onDeletePage && (
            <button
              onClick={async (e) => {
                e.stopPropagation();
                if (await confirm({ message: t("albumPage.confirmDeletePage"), confirmLabel: t("common.delete") })) {
                  onDeletePage();
                }
              }}
              data-testid={`page-delete-btn-${pageIndex}`}
              className="flex flex-col items-center gap-1 bg-[color:var(--coral)] text-[color:var(--paper)] px-1.5 py-2 hover:brightness-110 transition-all shadow-md"
              title={t("albumPage.deletePage")}
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      )}
      {showLayoutPicker && (
        <LayoutPicker
          onClose={() => setShowLayoutPicker(false)}
          onChoose={(patternName) => {
            onApplyLayout(patternName);
            setShowLayoutPicker(false);
          }}
        />
      )}
    </div>
  );
}
