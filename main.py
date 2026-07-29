from __future__ import annotations
import threading,time,traceback
from datetime import datetime,timezone,timedelta
from config import CHECK_INTERVAL,TELEGRAM_POLL_TIMEOUT,ADMIN_CHAT_ID
from core.registry import SITES
from core.storage import load,save,ensure_user,add_log,LOCK
from core.telegram import send,edit,answer,updates,esc
from core.filtering import matches,key
KST=timezone(timedelta(hours=9)); DB=load(); START=time.monotonic()
def now(): return datetime.now(KST)
def stamp(): return now().strftime('%Y-%m-%d %H:%M:%S')
def log(msg):
 line=f"[{stamp()}] {msg}"; print(line,flush=True)
 with LOCK:add_log(DB,line);save(DB)
def site_icon(ok): return '🟢' if ok else '🔴'
def settings_text(user):
 lines=['⚙️ <b>내 알림 설정</b>']
 for sid,(name,_) in SITES.items():
  c=user['sites'][sid]; hours=lambda v:'모든 시간' if v is None else (', '.join(f'{h:02d}~{h+2:02d}' for h in v) or '알림 안 함')
  lines += [f"\n{'✅' if c['enabled'] else '⬜'} <b>{name}</b>",f"코트: {esc(', '.join(map(str,c['courts'])))}",f"평일: {hours(c['weekday_hours'])} / 주말: {hours(c['weekend_hours'])}"]
 return '\n'.join(lines)
def main_keyboard(user):
 return {'inline_keyboard':[[{'text':f"{'✅' if user['sites'][s]['enabled'] else '⬜'} {n}",'callback_data':f'toggle:{s}'}] for s,(n,_) in SITES.items()]+[[{'text':'📊 상태','callback_data':'show:status'},{'text':'🧪 테스트','callback_data':'test'}],[{'text':'🎾 코트 설정','callback_data':'show:courts'},{'text':'⏰ 시간 설정','callback_data':'show:times'}]]}
def courts_keyboard(user):
 rows=[]
 vals={'yeonsu':['A','B','C'],'dalbit':list(range(5,15)),'saeachim':[1,2,3,4]}
 for sid,(name,_) in SITES.items():
  rows.append([{'text':f'— {name} —','callback_data':'noop'}])
  row=[]
  for v in vals[sid]:
   row.append({'text':f"{'✅' if v in user['sites'][sid]['courts'] else '⬜'} {v}",'callback_data':f'court:{sid}:{v}'})
   if len(row)==4: rows.append(row);row=[]
  if row:rows.append(row)
 rows.append([{'text':'⬅️ 설정','callback_data':'show:settings'}]);return {'inline_keyboard':rows}
def times_keyboard(user):
 rows=[]
 for sid,(name,_) in SITES.items():
  rows.append([{'text':f'— {name} —','callback_data':'noop'}])
  for typ,label in [('weekday_hours','평일'),('weekend_hours','주말')]:
   row=[{'text':label,'callback_data':'noop'}]
   current=user['sites'][sid][typ]
   for h in [6,8,10,12,14,16,18,20]:
    row.append({'text':f"{'✅' if current is not None and h in current else '⬜'}{h}",'callback_data':f'time:{sid}:{typ}:{h}'})
    if len(row)==5:rows.append(row);row=[]
   if row:rows.append(row)
   rows.append([{'text':f"{'✅' if current is None else '⬜'} {label} 모든 시간",'callback_data':f'time:{sid}:{typ}:all'}])
 rows.append([{'text':'⬅️ 설정','callback_data':'show:settings'}]);return {'inline_keyboard':rows}
def status_text():
 lines=['📊 <b>ChaenissBot v8 상태</b>',f'가동: {int((time.monotonic()-START)//60)}분',f"검사: {DB['stats']['checks']}회 / 알림: {DB['stats']['alerts']}회",f"사용자: {len(DB['users'])}명",'']
 for sid,(name,_) in SITES.items():
  x=DB['site_status'].get(sid,{}); lines.append(f"{site_icon(x.get('ok',False))} {name}: {x.get('slots','-')}개 / {x.get('elapsed','-')}초")
  if x.get('errors'):lines.append('  '+esc(x['errors'][-1])[:180])
 return '\n'.join(lines)
def slot_text(s): return f"🎾 <b>{esc(s.get('court'))}</b>\n📅 {esc(s.get('date'))}\n🕐 {esc(s.get('time'))}\n👉 <a href=\"{esc(s.get('url'))}\"><b>예약하러 가기</b></a>"
def notify_user(chat_id,slots):
 chunks=[];cur=f"🚨 <b>신규 빈자리 {len(slots)}개!</b>\n\n"
 for s in slots:
  b=slot_text(s)+'\n\n'
  if len(cur)+len(b)>3600:chunks.append(cur);cur='📋 <b>[이어서]</b>\n\n'+b
  else:cur+=b
 chunks.append(cur+f'⏰ {stamp()}')
 return all(send(chat_id,c) for c in chunks)
def monitor_once():
 results={}; allslots=[]
 for sid,(name,collector) in SITES.items():
  try:r=collector()
  except Exception as e:
   from core.models import SiteResult
   r=SiteResult(sid,name,[],[f'{type(e).__name__}: {e}'],0)
  results[sid]=r; allslots.extend(r.slots); DB['site_status'][sid]=r.to_status();log(f"{site_icon(r.ok)} {name}: {len(r.slots)}개, 오류 {len(r.errors)}")
 DB['stats']['checks']+=1;DB['stats']['errors']+=sum(not r.ok for r in results.values())
 for chat_id,user in list(DB['users'].items()):
  targets={key(s):s for s in allslots if matches(s,user)}; old=set(user.get('current_keys',[])); newkeys=set(targets)-old
  first=bool(user.pop('created',False))
  user['current_keys']=sorted(targets)
  if first: send(chat_id,'🟢 <b>ChaenissBot v8 등록 완료</b>\n\n'+settings_text(user),main_keyboard(user))
  elif newkeys:
   slots=[targets[k] for k in sorted(newkeys)]
   if notify_user(chat_id,slots):DB['stats']['alerts']+=1
 save(DB)
def monitor_loop():
 while True:
  t=time.monotonic()
  try:monitor_once()
  except Exception as e:log(f"감시 루프 오류: {type(e).__name__}: {e}\n{traceback.format_exc()[-1000:]}")
  time.sleep(max(1,CHECK_INTERVAL-(time.monotonic()-t)))
def handle_message(m):
 chat=m.get('chat',{}); cid=str(chat.get('id')); text=(m.get('text') or '').split()[0]; user=ensure_user(DB,cid,chat.get('first_name') or '사용자');save(DB)
 if text in ['/start','/settings']:send(cid,settings_text(user),main_keyboard(user))
 elif text in ['/status','/health']:send(cid,status_text())
 elif text=='/logs':send(cid,'📜 <b>최근 로그</b>\n\n'+esc('\n'.join(DB['logs'][-15:])))
 elif text=='/test':send(cid,'🧪 <b>테스트 알림 정상</b>\nTelegram 연결과 사용자별 전송이 정상입니다.')
 else:send(cid,'명령어: /settings /status /logs /test')
def handle_callback(q):
 cid=str(q['message']['chat']['id']);mid=q['message']['message_id'];data=q.get('data','');user=ensure_user(DB,cid,q.get('from',{}).get('first_name','사용자'))
 if data.startswith('toggle:'):
  sid=data.split(':')[1];user['sites'][sid]['enabled']=not user['sites'][sid]['enabled'];user['current_keys']=[];edit(cid,mid,settings_text(user),main_keyboard(user))
 elif data=='show:settings':edit(cid,mid,settings_text(user),main_keyboard(user))
 elif data=='show:status':edit(cid,mid,status_text(),{'inline_keyboard':[[{'text':'⬅️ 설정','callback_data':'show:settings'}]]})
 elif data=='show:courts':edit(cid,mid,'🎾 <b>코트 설정</b>\n선택한 코트만 알림을 받습니다.',courts_keyboard(user))
 elif data=='show:times':edit(cid,mid,'⏰ <b>시간 설정</b>\n숫자는 시작 시간입니다.',times_keyboard(user))
 elif data.startswith('court:'):
  _,sid,raw=data.split(':');v=raw if sid=='yeonsu' else int(raw);lst=user['sites'][sid]['courts']; lst.remove(v) if v in lst and len(lst)>1 else (lst.append(v) if v not in lst else None);user['current_keys']=[];edit(cid,mid,'🎾 <b>코트 설정</b>',courts_keyboard(user))
 elif data.startswith('time:'):
  _,sid,typ,raw=data.split(':');cur=user['sites'][sid][typ]
  if raw=='all':user['sites'][sid][typ]=None
  else:
   h=int(raw);cur=[] if cur is None else cur;cur.remove(h) if h in cur else cur.append(h);user['sites'][sid][typ]=sorted(cur)
  user['current_keys']=[];edit(cid,mid,'⏰ <b>시간 설정</b>',times_keyboard(user))
 elif data=='test':send(cid,'🧪 <b>테스트 알림 정상</b>')
 save(DB);answer(q['id'],'저장했어요')
def telegram_loop():
 while True:
  for u in updates(int(DB.get('telegram_offset',0)),TELEGRAM_POLL_TIMEOUT):
   DB['telegram_offset']=u['update_id']+1
   try:
    if 'message' in u:handle_message(u['message'])
    elif 'callback_query' in u:handle_callback(u['callback_query'])
   except Exception as e:log(f"명령 처리 오류: {e}")
   save(DB)
def run():
 log('ChaenissBot v8.0 modular multi-user 시작')
 if ADMIN_CHAT_ID: ensure_user(DB,ADMIN_CHAT_ID,'관리자');save(DB)
 threading.Thread(target=telegram_loop,daemon=True).start();monitor_loop()
if __name__=='__main__':run()
