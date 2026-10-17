import { extractText, getDocumentProxy } from 'unpdf';
import { unzipSync, strFromU8 } from 'fflate';
// Pulls plain text out of uploaded documents so the AI review can read them.
// Pictures, videos and scanned (image-only) PDFs are reported as skipped.
export const PER_FILE=25000, TOTAL=60000, MAX_FILES=8;
export type Extracted={name:string;text:string;truncated:boolean};
export type Skipped={name:string;reason:string};
const decodeXml=(s:string)=>s.replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&apos;/g,"'").replace(/&#(\d+);/g,(_,n)=>String.fromCharCode(+n)).replace(/&amp;/g,'&');
export function docxText(bytes:Uint8Array){
 const xml=strFromU8(unzipSync(bytes,{filter:f=>f.name==='word/document.xml'})['word/document.xml']||new Uint8Array());
 return decodeXml(xml.replace(/<w:tab\/>/g,'\t').replace(/<w:br\/>|<\/w:p>/g,'\n').replace(/<[^>]+>/g,''));
}
export async function pdfText(bytes:Uint8Array){const {text}=await extractText(await getDocumentProxy(bytes),{mergePages:true});return text as string;}
export async function fileText(name:string,mime:string,bytes:Uint8Array):Promise<string|null>{
 if(mime==='text/plain'||mime==='text/markdown')return new TextDecoder().decode(bytes);
 if(mime==='application/pdf')return pdfText(bytes);
 if(mime==='application/vnd.openxmlformats-officedocument.wordprocessingml.document')return docxText(bytes);
 return null;
}
/** files: {name,mime,load()} in display order. Returns what was read (capped) and what was skipped, with reasons. */
export async function extractAll(files:{name:string;mime:string;load:()=>Promise<Uint8Array>}[]){
 const read:Extracted[]=[],skipped:Skipped[]=[];let budget=TOTAL;
 for(const f of files){
  if(f.mime.startsWith('image/')||f.mime.startsWith('video/')){skipped.push({name:f.name,reason:f.mime.startsWith('image/')?'picture':'video'});continue;}
  if(read.length>=MAX_FILES||budget<=0){skipped.push({name:f.name,reason:'review length limit reached'});continue;}
  try{
   const raw=(await fileText(f.name,f.mime,await f.load()))?.replace(/[ \t]+/g,' ').replace(/\n{3,}/g,'\n\n').trim();
   if(raw===undefined||raw===null){skipped.push({name:f.name,reason:'unsupported type'});continue;}
   if(raw.length<20){skipped.push({name:f.name,reason:'no readable text (scanned or empty)'});continue;}
   const cap=Math.min(PER_FILE,budget);read.push({name:f.name,text:raw.slice(0,cap),truncated:raw.length>cap});budget-=Math.min(raw.length,cap);
  }catch{skipped.push({name:f.name,reason:'could not be read'});}
 }
 return {read,skipped};
}
export function scopeNote(read:Extracted[],skipped:Skipped[]){
 const r=read.length?`Read: ${read.map(f=>f.name+(f.truncated?' (first part only)':'')).join(', ')}.`:'No attachments were read.';
 const s=skipped.length?` Not read — needs human review: ${skipped.map(f=>`${f.name} (${f.reason})`).join(', ')}.`:'';
 return `Editor text${read.length?' and attached document text':' only'}. ${r}${s}`;
}
