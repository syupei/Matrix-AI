#!/usr/bin/env python3
"""Read the explicit delivery list; this proves bytes read, not authorship or quality."""
import argparse
import hashlib
import json
from pathlib import Path

FORMAT='delivery-readback/1'


def require(condition,message):
    if not condition:raise ValueError(message)


def location(root,name):
    require(isinstance(name,str) and name.strip(),'路径不能为空')
    path=Path(name)
    require(not path.is_absolute() and '..' not in path.parts and path.as_posix()==name,
            '须使用项目内规范相对路径: '+name)
    root=Path(root).resolve();target=root/path
    require(target.resolve().is_relative_to(root),'路径越过项目边界: '+name)
    require(not any(p.is_symlink() for p in (target,*target.parents) if p!=root),'不读取符号链接: '+name)
    return target


def read_one(root,kind,name,marker,expected=None):
    require(isinstance(kind,str) and bool(kind.strip()),'须注明交付种类')
    target=location(root,name)
    require(target.is_file(),'待核对的项目记录不存在: '+name)
    require(target.stat().st_nlink==1,'不读取硬链接别名: '+name)
    data=target.read_bytes()
    require(isinstance(marker,str) and marker.strip() and marker in data.decode('utf-8'),
            '记录内容未找到指定标题或条目 ID: '+str(marker))
    digest=hashlib.sha256(data).hexdigest()
    require(expected is None or expected==digest,'回读后内容已变更: '+name)
    return dict(kind=kind,path=name,marker=marker,sha256=digest)


def read_batch(root,items):
    require(isinstance(items,list) and items,'交付清单 items 须为非空列表')
    names=[item.get('path') for item in items if isinstance(item,dict)]
    require(len(names)==len(items) and all(isinstance(p,str) for p in names),'每项须有 path')
    require(len(set(names))==len(names),'交付清单不能重复列同一路径')
    results=[];identities=set()
    for item in items:
        row={key:item.get(key) for key in ('kind','path','marker')}
        try:
            row.update(read_one(root,row['kind'],row['path'],row['marker'],item.get('sha256')))
            stat=location(root,row['path']).stat();identity=(stat.st_dev,stat.st_ino)
            require(identity not in identities,'交付清单通过别名重复列出同一文件: '+row['path'])
            identities.add(identity)
            row['status']='saved_readback'
        except (ValueError,OSError,UnicodeError) as error:
            row.update(status='unverified',error=str(error))
            # Existence is separate from successful content readback. No claim for unsafe aliases.
            try:
                path=location(root,row['path'])
                row['status']='saved_unread' if path.is_file() and path.stat().st_nlink==1 else 'missing' if not path.exists() else 'unverified'
            except (ValueError,OSError):pass
        results.append(row)
    return dict(format=FORMAT,complete=all(r['status']=='saved_readback' for r in results),
                checked_count=sum(r['status']=='saved_readback' for r in results),results=results,
                limitation='Only the listed text files were read. Omitted files, authorship, understanding and professional quality are not verified.')


def load(path):
    def unique(pairs):
        result={}
        for key,value in pairs:
            require(key not in result,'重复 JSON 字段: '+key);result[key]=value
        return result
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--manifest',help='项目内清单 JSON: {"items":[{"path":...,"kind":...,"marker":...}]}')
    group.add_argument('--verify',help='项目内已保存的回读结果；按原摘要逐份重读')
    args=parser.parse_args()
    try:
        root=Path(args.root).resolve();require(root.is_dir(),'项目根目录不存在')
        value=load(location(root,args.manifest or args.verify))
        if args.verify:
            require(value.get('format')==FORMAT and value.get('complete') is True,'只核对先前完整的回读结果')
            items=value.get('results')
            require(isinstance(items,list) and all(isinstance(row,dict) and isinstance(row.get('sha256'),str) and len(row['sha256'])==64 for row in items),'回读结果缺少逐份摘要')
        else:items=value.get('items')
        result=read_batch(root,items);print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result['complete'] else 1
    except (ValueError,OSError,TypeError,AttributeError) as error:
        print(json.dumps(dict(format=FORMAT,complete=False,error=str(error)),ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
