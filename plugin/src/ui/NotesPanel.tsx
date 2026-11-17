import { useEffect } from "react";
import type { ReaderController, UIState } from "../reader/controller";
import { openNote } from "../zotero/api";
import { Empty } from "./common";

export function NotesPanel(props: { controller: ReaderController; state: UIState }): JSX.Element {
  const { controller, state } = props;

  useEffect(() => {
    void controller.refreshNotes();
  }, [controller]);

  return (
    <div className="pl-scroll">
      <div className="pl-row pl-row--between" style={{ marginBottom: 8 }}>
        <span className="pl-small pl-muted">本篇论文的 PaperLoom 笔记（{state.notes.length}）</span>
        <span className="pl-row">
          <button
            type="button"
            className="pl-btn"
            disabled={!state.messages.length}
            onClick={() => void controller.saveConversationNote()}
          >
            保存整段对话
          </button>
          <button type="button" className="pl-btn pl-btn--ghost" onClick={() => void controller.refreshNotes()}>
            刷新
          </button>
        </span>
      </div>
      {!state.notes.length ? (
        <Empty text="还没有笔记。回答下方的“保存笔记”，或选中文字后点击“保存笔记”即可写入 Zotero 子笔记。" />
      ) : (
        state.notes.map((note) => (
          <div key={note.id} className="pl-card" style={{ cursor: "pointer" }} onClick={() => openNote(note.id)}>
            <div className="pl-small" style={{ marginBottom: 4 }}>
              <span className="pl-badge">Zotero 笔记</span>
            </div>
            <div className="pl-small">{note.snippet || "(空笔记)"}</div>
          </div>
        ))
      )}
      <div className="pl-card pl-small pl-muted">
        提示：重复保存同一回答会更新已有笔记，而不是新建一条。
      </div>
    </div>
  );
}
