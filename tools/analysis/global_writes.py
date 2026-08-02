"""AST-based detection of writes to global variables (missing `local`) anywhere in code.
Tracks lexical scopes; reports Name-target assignments not resolvable to a local."""
import os, sys, concurrent.futures

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (tools/<sub>/<script>)
# globals that are legitimately written by addons
ALLOWED = {
    # SavedVariables / addon exports
    'ElvUI', 'ElvDB', 'ElvPrivateDB', 'ElvCharacterDB', 'ElvUF', 'oUF',
    'AddOnSkins', 'EnhancedFriendsList_Data',
    # Blizzard globals commonly re-assigned by UI addons on purpose
    'StaticPopupDialogs', 'UIDROPDOWNMENU_OPEN_MENU', 'UIDROPDOWNMENU_INIT_MENU',
    'UIDROPDOWNMENU_MENU_LEVEL', 'UIDROPDOWNMENU_MENU_VALUE', 'UIDROPDOWNMENU_SHOW_TIME',
    'GameTooltipHeaderText', 'GameTooltipText', 'GameTooltipTextSmall',
    'CONTAINER_OFFSET_X', 'CONTAINER_OFFSET_Y', 'TOOLTIP_UPDATE_TIME',
    'CHAT_TAB_HIDE_DELAY', 'CHAT_FRAME_FADE_TIME', 'CHAT_FRAME_FADE_OUT_TIME',
    'CHAT_FONT_HEIGHTS', 'DEFAULT_CHATFRAME_ALPHA', 'GENERAL_CHAT_DOCK',
    'RAID_CLASS_COLORS', 'CUSTOM_CLASS_COLORS', 'MAX_HOTZONETEXT_LINE',
    'WORLDFRAME_SETPOINT_USED',
}
ALLOWED_PREFIX = ('SLASH_', 'BINDING_', 'StaticPopup', 'ITEM_QUALITY')

def check(path):
    from luaparser import ast, astnodes
    rel = os.path.relpath(path, ROOT)
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            src = f.read().lstrip('﻿')
        tree = ast.parse(src)
    except Exception:
        return []

    findings = []

    class Scope:
        def __init__(self, parent):
            self.parent = parent
            self.names = set()
        def declare(self, n): self.names.add(n)
        def resolves(self, n):
            s = self
            while s:
                if n in s.names: return True
                s = s.parent
            return False

    def walk_block(body, scope):
        for stmt in body.body if hasattr(body, 'body') else body:
            walk_stmt(stmt, scope)

    def handle_func_body(node, scope, self_implicit=False):
        fs = Scope(scope)
        for a in getattr(node, 'args', []) or []:
            if isinstance(a, astnodes.Name):
                fs.declare(a.id)
            elif isinstance(a, astnodes.Varargs):
                pass
        if self_implicit:
            fs.declare('self')
        walk_block(node.body, fs)

    def walk_expr(node, scope):
        if node is None: return
        if isinstance(node, astnodes.AnonymousFunction):
            handle_func_body(node, scope)
        elif isinstance(node, (astnodes.Function, astnodes.Method)):
            pass
        else:
            for child in getattr(node, '__dict__', {}).values():
                if isinstance(child, astnodes.Node):
                    walk_expr(child, scope)
                elif isinstance(child, list):
                    for c in child:
                        if isinstance(c, astnodes.Node):
                            walk_expr(c, scope)

    def walk_stmt(stmt, scope):
        t = astnodes
        if isinstance(stmt, t.LocalAssign):
            for v in stmt.values or []:
                walk_expr(v, scope)
            for tg in stmt.targets:
                if isinstance(tg, t.Name):
                    scope.declare(tg.id)
        elif isinstance(stmt, t.Assign):
            for v in stmt.values or []:
                walk_expr(v, scope)
            for tg in stmt.targets:
                if isinstance(tg, t.Name) and not scope.resolves(tg.id):
                    nm = tg.id
                    if nm not in ALLOWED and not any(nm.startswith(p) for p in ALLOWED_PREFIX):
                        findings.append((getattr(stmt, 'line', getattr(tg, 'line', 0)), nm))
                else:
                    walk_expr(tg, scope)
        elif isinstance(stmt, t.LocalFunction):
            if isinstance(stmt.name, t.Name):
                scope.declare(stmt.name.id)
            handle_func_body(stmt, scope)
        elif isinstance(stmt, t.Function):
            # global or table-field function
            if isinstance(stmt.name, t.Name) and not scope.resolves(stmt.name.id):
                nm = stmt.name.id
                if nm not in ALLOWED and not any(nm.startswith(p) for p in ALLOWED_PREFIX):
                    findings.append((getattr(stmt, 'line', 0), nm + ' (function)'))
            handle_func_body(stmt, scope)
        elif isinstance(stmt, t.Method):
            handle_func_body(stmt, scope, self_implicit=True)
        elif isinstance(stmt, (t.While, t.Repeat)):
            walk_expr(getattr(stmt, 'test', None), scope)
            walk_block(stmt.body, Scope(scope))
        elif isinstance(stmt, t.If):
            walk_expr(stmt.test, scope)
            walk_block(stmt.body, Scope(scope))
            orelse = stmt.orelse
            while isinstance(orelse, t.ElseIf):
                walk_expr(orelse.test, scope)
                walk_block(orelse.body, Scope(scope))
                orelse = orelse.orelse
            if orelse is not None:
                if isinstance(orelse, t.Block):
                    walk_block(orelse, Scope(scope))
                elif isinstance(orelse, list):
                    walk_block(orelse, Scope(scope))
        elif isinstance(stmt, t.Fornum):
            fscope = Scope(scope)
            if isinstance(stmt.target, t.Name):
                fscope.declare(stmt.target.id)
            for e in (stmt.start, stmt.stop, stmt.step):
                walk_expr(e, scope)
            walk_block(stmt.body, fscope)
        elif isinstance(stmt, t.Forin):
            fscope = Scope(scope)
            for tg in stmt.targets:
                if isinstance(tg, t.Name):
                    fscope.declare(tg.id)
            for e in stmt.iter if isinstance(stmt.iter, list) else [stmt.iter]:
                walk_expr(e, scope)
            walk_block(stmt.body, fscope)
        elif isinstance(stmt, t.Do):
            walk_block(stmt.body, Scope(scope))
        elif isinstance(stmt, t.Return):
            for v in stmt.values or []:
                walk_expr(v, scope)
        else:
            walk_expr(stmt, scope)

    root_scope = Scope(None)
    root_scope.declare('...')
    walk_block(tree.body, root_scope)
    return [(rel, ln, nm) for ln, nm in findings]

def collect():
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        if os.sep + 'Libraries' + os.sep in dirpath + os.sep:
            continue
        for fn in filenames:
            if fn.lower().endswith('.lua'):
                files.append(os.path.join(dirpath, fn))
    return files

if __name__ == '__main__':
    files = collect()
    print(f"analyzing {len(files)} files (Libraries excluded)...", flush=True)
    allf = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=8) as ex:
        for res in ex.map(check, files, chunksize=4):
            allf.extend(res)
    print(f"\n=== GLOBAL WRITES (potential missing `local`): {len(allf)} ===")
    for rel, ln, nm in allf:
        print(f"{rel}:{ln}: {nm}")
