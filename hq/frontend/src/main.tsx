import React from 'react';import {createRoot} from 'react-dom/client';import {createBrowserRouter,RouterProvider,useRouteError} from 'react-router-dom';
import '@fontsource/inter/latin-400.css';import '@fontsource/inter/latin-500.css';import '@fontsource/inter/latin-600.css';import '@fontsource/inter/latin-700.css';
import {Provider} from './api';import App from './App';import './styles.css';
class Boundary extends React.Component<{children:React.ReactNode},{error:boolean}>{state={error:false};static getDerivedStateFromError(){return {error:true}}render(){return this.state.error?<main className="fatal"><h1>Something interrupted the workspace.</h1><p>Your saved work is still stored. Reload to reconnect.</p><button onClick={()=>location.reload()}>Reload workspace</button></main>:this.props.children}}
// A tab opened before a deploy can ask for a code chunk the new deploy replaced.
// Reload once to pick up the current build; the flag prevents a reload loop.
const STALE=/dynamically imported module|Importing a module script failed|error loading dynamically imported/i;
const reloadOnce=()=>{if(sessionStorage.getItem('hq-chunk-reload'))return false;sessionStorage.setItem('hq-chunk-reload','1');location.reload();return true};
window.addEventListener('vite:preloadError',e=>{if(reloadOnce())e.preventDefault()});
setTimeout(()=>sessionStorage.removeItem('hq-chunk-reload'),15000);
function RouteError(){const err=useRouteError() as any;const msg=String(err?.message||err||'');if(STALE.test(msg)&&reloadOnce())return null;return <main className="fatal"><h1>Something interrupted the workspace.</h1><p>{STALE.test(msg)?'HQ was just updated. Reload to get the latest version.':'Your saved work is still stored. Reload to reconnect.'}</p><button onClick={()=>location.reload()}>Reload workspace</button></main>}
createRoot(document.getElementById('root')!).render(<React.StrictMode><Boundary><RouterProvider router={createBrowserRouter([{path:'*',element:<Provider><App/></Provider>,errorElement:<RouteError/>}],{basename:import.meta.env.BASE_URL.replace(/\/$/,'')||'/'})}/></Boundary></React.StrictMode>);
