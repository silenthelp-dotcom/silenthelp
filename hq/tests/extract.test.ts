import {describe,it,expect} from 'vitest';
import {zipSync,strToU8} from 'fflate';
import {extractAll,docxText,pdfText,scopeNote,PER_FILE} from '../backend/services/extract';
// Minimal one-page PDF with a text object; xref offsets computed so the parser accepts it.
function tinyPdf(text:string){const objs=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>','<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',`<< /Length ${`BT /F1 12 Tf 72 720 Td (${text}) Tj ET`.length} >>\nstream\nBT /F1 12 Tf 72 720 Td (${text}) Tj ET\nendstream`,'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];let out='%PDF-1.4\n';const offs:number[]=[];objs.forEach((o,i)=>{offs.push(out.length);out+=`${i+1} 0 obj\n${o}\nendobj\n`});const x=out.length;out+=`xref\n0 ${objs.length+1}\n0000000000 65535 f \n${offs.map(o=>String(o).padStart(10,'0')+' 00000 n \n').join('')}trailer\n<< /Size ${objs.length+1} /Root 1 0 R >>\nstartxref\n${x}\n%%EOF`;return strToU8(out)}
const docx=(body:string)=>zipSync({'word/document.xml':strToU8(`<w:document><w:body>${body}</w:body></w:document>`)});
const DOCX='application/vnd.openxmlformats-officedocument.wordprocessingml.document';
describe('attachment text extraction',()=>{
 it('reads Word paragraphs and decodes entities',()=>{expect(docxText(docx('<w:p><w:r><w:t>Survey of 40 students</w:t></w:r></w:p><w:p><w:r><w:t>Q&amp;A notes</w:t></w:r></w:p>'))).toBe('Survey of 40 students\nQ&A notes\n')});
 it('reads PDF text',async()=>{expect(await pdfText(tinyPdf('Pilot interview findings'))).toContain('Pilot interview findings')});
 it('reads documents, skips pictures and videos, caps length, and reports scope',async()=>{
  const files=[{name:'notes.md',mime:'text/markdown',load:async()=>strToU8('# Findings\n'+'x'.repeat(PER_FILE+500))},{name:'brief.docx',mime:DOCX,load:async()=>docx('<w:p><w:r><w:t>Interview summary with three themes.</w:t></w:r></w:p>')},{name:'photo.png',mime:'image/png',load:async()=>new Uint8Array()},{name:'clip.mp4',mime:'video/mp4',load:async()=>new Uint8Array()},{name:'scan.pdf',mime:'application/pdf',load:async()=>tinyPdf('')},{name:'broken.pdf',mime:'application/pdf',load:async()=>strToU8('%PDF-1.4 garbage')}];
  const {read,skipped}=await extractAll(files);
  expect(read.map(r=>r.name)).toEqual(['notes.md','brief.docx']);expect(read[0].truncated).toBe(true);expect(read[0].text.length).toBe(PER_FILE);
  expect(skipped.map(s=>s.name)).toEqual(['photo.png','clip.mp4','scan.pdf','broken.pdf']);
  const note=scopeNote(read,skipped);expect(note).toContain('notes.md (first part only)');expect(note).toContain('clip.mp4 (video)');
 });
});
