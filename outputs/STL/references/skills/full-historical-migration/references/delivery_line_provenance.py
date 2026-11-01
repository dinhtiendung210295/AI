"""Pure frozen-source provenance gate; never chooses an arbitrary SO line."""
def issues(move_ids, moves):
    allowed=set(move_ids)
    errors=[]
    for mid in move_ids:
        seen=set();frontier=[mid];lines=set()
        while frontier:
            current=frontier.pop()
            if current in seen:continue
            seen.add(current);row=moves[current]
            line=row.get('sale_line_id')
            if line:lines.add(line[0] if isinstance(line,(list,tuple)) else line)
            frontier.extend(i for i in row.get('move_dest_ids',[]) if i in allowed)
        if len(lines)!=1:
            errors.append({'source_move':mid,'downstream_source_lines':sorted(lines),'reason':'shared_internal_so_lines_require_merge_support' if lines else 'missing_downstream_so_line'})
    return errors
