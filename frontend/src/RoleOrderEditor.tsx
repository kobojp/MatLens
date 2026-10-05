import { useRef, useState } from "react";
import { moveItem } from "./utils";

type Props = {
  /** 目前使用中的角色，依順序排列 */
  roles: string[];
  /** 所有可用角色 */
  allRoles: string[];
  onChange: (roles: string[]) => void;
};

type Origin = { role: string; from: "used" | "pool" };

export default function RoleOrderEditor({ roles, allRoles, onChange }: Props) {
  const dragged = useRef<Origin | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);
  const pool = allRoles.filter((role) => !roles.includes(role));

  function insertAt(role: string, index: number) {
    const without = roles.filter((item) => item !== role);
    const target = Math.min(index, without.length);
    onChange([...without.slice(0, target), role, ...without.slice(target)]);
  }

  function remove(role: string) {
    if (roles.length <= 1) return; // 至少保留一個角色
    onChange(roles.filter((item) => item !== role));
  }

  function endDrag() {
    dragged.current = null;
    setOverIndex(null);
  }

  return (
    <details className="role-order">
      <summary>預設角色順序</summary>
      <p className="role-order-help">
        拖曳方塊排序。拉進照片時，依此順序從第一個角色開始分配；照片比角色多時，多出的沿用最後一個角色。
      </p>
      <div
        className="role-order-used"
        role="list"
        aria-label="使用中的角色順序"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          if (dragged.current) insertAt(dragged.current.role, roles.length);
          endDrag();
        }}
      >
        {roles.map((role, index) => (
          <span
            key={role}
            role="listitem"
            className={`role-chip ${overIndex === index ? "over" : ""}`}
            draggable
            onDragStart={() => { dragged.current = { role, from: "used" }; }}
            onDragOver={(event) => { event.preventDefault(); setOverIndex(index); }}
            onDragEnd={endDrag}
            onDrop={(event) => {
              event.preventDefault();
              event.stopPropagation();
              if (dragged.current) insertAt(dragged.current.role, index);
              endDrag();
            }}
          >
            <span className="role-chip-index">{index + 1}</span>
            <strong>{role}</strong>
            <button type="button" aria-label={`${role} 往前移`} disabled={index === 0} onClick={() => onChange(moveItem(roles, index, index - 1))}>◀</button>
            <button type="button" aria-label={`${role} 往後移`} disabled={index === roles.length - 1} onClick={() => onChange(moveItem(roles, index, index + 1))}>▶</button>
            <button type="button" aria-label={`不使用 ${role}`} disabled={roles.length <= 1} onClick={() => remove(role)}>×</button>
          </span>
        ))}
      </div>
      <div
        className="role-order-pool"
        role="list"
        aria-label="不使用的角色"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          if (dragged.current) remove(dragged.current.role);
          endDrag();
        }}
      >
        <span className="role-order-pool-label">不使用（拖到這裡移除）</span>
        {pool.map((role) => (
          <span
            key={role}
            role="listitem"
            className="role-chip pool"
            draggable
            onDragStart={() => { dragged.current = { role, from: "pool" }; }}
            onDragEnd={endDrag}
          >
            <strong>{role}</strong>
            <button type="button" aria-label={`加入 ${role}`} onClick={() => onChange([...roles, role])}>＋</button>
          </span>
        ))}
      </div>
    </details>
  );
}
