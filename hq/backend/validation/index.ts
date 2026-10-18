import { z } from 'zod';
const id=z.string().uuid(); const optionalId=z.union([id,z.literal('')]).optional();
const date=z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine(v=>!isNaN(Date.parse(v)) && new Date(v).toISOString().slice(0,10)===v,'Invalid date');
const text=z.string().max(20000); const title=z.string().trim().min(1).max(200);
export const researchSchema=z.object({title,summary:text,findings:z.string().max(150000),methodology:text,sources:z.array(z.string().url().refine(u=>/^https?:\/\//.test(u))).max(100),limitations:text,recommendations:text,notes:text});
const taskFields={title,description:text,project_id:optionalId,department_id:optionalId,priority:z.enum(['low','medium','high','urgent']),start_date:z.union([date,z.literal('')]).optional(),due_date:date,assignees:z.array(id).min(1).max(50).refine(a=>new Set(a).size===a.length),details:z.object({deliverables:text,questions:text,required_sources:text,criteria:text,instructions:text}),dependencies:z.array(id).max(50).default([])};
export const schemas={
 'task.create':z.object(taskFields).refine(t=>!t.start_date||t.start_date<=t.due_date,'Start date must be before deadline'),
 'task.delete':z.object({id}),
'task.update':z.object({id,title,description:text,priority:taskFields.priority,due_date:date,assignees:taskFields.assignees.optional()}),
 'assignment.start':z.object({task_id:id}), 'assignment.complete':z.object({task_id:id,user_id:id}),
 'comment.add':z.object({task_id:id,body:z.string().trim().min(1).max(10000),kind:z.enum(['comment','progress','extension'])}),
 'draft.save':z.object({task_id:id,revision:z.number().int().nonnegative(),content:researchSchema}),
 'submission.submit':z.object({task_id:id,revision:z.number().int().nonnegative()}),
 'submission.review':z.object({id,version_id:id,decision:z.enum(['under_review','revision_requested','approved','rejected']),feedback:z.string().trim().min(3).max(20000)}),
 'employee.update':z.object({id,full_name:title,role:z.enum(['admin','employee']),active:z.boolean(),department_id:optionalId}),
 'profile.update':z.object({full_name:title,bio:z.string().trim().max(600).optional()}),
 'avatar.prepare':z.object({name:z.string().min(1).max(240),size:z.number().int().positive()}), 'avatar.finish':z.object({path:z.string().min(1).max(300)}), 'avatar.remove':z.object({}), 'snapshot.download':z.object({id}), 'snapshot.run':z.object({}), 'notification.read':z.object({id}),
 'project.save':z.object({id:optionalId,name:title,description:text,owner_id:optionalId,start_date:z.union([date,z.literal('')]).optional(),target_date:date,status:z.enum(['active','paused','completed']),members:z.array(id).max(100)}),
 'milestone.save':z.object({id:optionalId,project_id:optionalId,title,target_date:date,completed:z.boolean(),risk:text}),
 'department.create':z.object({name:title}),
 'invite':z.object({email:z.string().email().max(254),full_name:title,role:z.enum(['admin','employee']),department_id:optionalId,temporary_password:z.string().min(12).max(128).optional()}),
 'password.change':z.object({password:z.string().min(12).max(128)}),
 'ai.review':z.object({version_id:id}),
 'file.download':z.object({id,kind:z.enum(['task','submission'])}),
 'file.prepare':z.object({kind:z.enum(['task','submission']),record_id:id,name:z.string().min(1).max(240),size:z.number().int().positive()}),
 'file.finish':z.object({kind:z.enum(['task','submission']),record_id:id,path:z.string().min(1).max(600),name:z.string().min(1).max(240)})
};
export type Operation=keyof typeof schemas;
export function validateCommand(op:string,payload:unknown){if(!(op in schemas)) throw new Error('Unknown operation');return schemas[op as Operation].parse(payload);}
export const fileTypes:Record<string,string>={pdf:'application/pdf',docx:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',txt:'text/plain',md:'text/markdown',png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',webp:'image/webp',mp4:'video/mp4',mov:'video/quicktime',webm:'video/webm'};
export const MB=1024*1024;
export const maxBytes=(ext:string)=>['mp4','mov','webm'].includes(ext)?50*MB:10*MB;
export const fileHelp='Documents and pictures up to 10 MB (PDF, DOCX, TXT, MD, PNG, JPEG, WebP); videos up to 50 MB (MP4, MOV, WebM).';
export function validateFile(name:string,size:number,bytes?:Uint8Array){const ext=name.split('.').pop()?.toLowerCase()||'';if(!fileTypes[ext]||name.length>240||size<1)throw new Error(fileHelp);if(size>maxBytes(ext))throw new Error(`${name} is too large. ${fileHelp}`);if(bytes){const starts=(a:number[])=>a.every((b,i)=>bytes[i]===b);const sig=new TextDecoder().decode(bytes.slice(0,16));const box=sig.slice(4,8);if((ext==='pdf'&&!sig.startsWith('%PDF-'))||(ext==='docx'&&!starts([80,75,3,4]))||(ext==='png'&&!starts([137,80,78,71,13,10,26,10]))||(['jpg','jpeg'].includes(ext)&&!starts([255,216,255]))||(ext==='webp'&&!(sig.startsWith('RIFF')&&sig.slice(8,12)==='WEBP'))||(ext==='mp4'&&box!=='ftyp')||(ext==='mov'&&!['ftyp','moov','wide','mdat','free','skip'].includes(box))||(ext==='webm'&&!starts([26,69,223,163]))||(['txt','md'].includes(ext)&&bytes.includes(0)))throw new Error('File contents do not match the extension.');}return fileTypes[ext];}
export function validateAvatar(name:string,size:number,bytes?:Uint8Array){const ext=name.split('.').pop()?.toLowerCase()||'';if(!['png','jpg','jpeg','webp'].includes(ext))throw new Error('Use a PNG, JPEG or WebP photo.');if(size>5*MB)throw new Error('Photos can be up to 5 MB.');return validateFile(name,size,bytes);}
export const authorshipWarning='AI authorship assessments are uncertain and cannot establish whether a person used AI. Do not use these indicators alone to accuse, penalize, or reject a contributor.';
const section=z.object({assessment:z.enum(['strong','partial','insufficient']),explanation:z.string().max(5000)});
export const aiResultSchema=z.object({completeness:section,evidence_quality:section,source_credibility:section,reasoning:section,clarity:section,inconsistencies:z.array(z.string()),strengths:z.array(z.string()),weaknesses:z.array(z.string()),missing_evidence:z.array(z.string()),unsupported_claims:z.array(z.string()),suggested_revisions:z.array(z.string()),authorship_indicators:z.array(z.string()),ai_written_estimate:z.number().min(0).max(100).optional(),limitations:z.string()});
