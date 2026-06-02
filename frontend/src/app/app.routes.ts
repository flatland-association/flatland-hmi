import { Routes } from '@angular/router'
import { MapComponent } from './map/map.component'
import {environment} from '../environments/environment';
import {AppComponent} from './app.component';

export const routes: Routes = [
  { path: '', redirectTo: 'full', pathMatch: 'full' },
  { path: 'full', component: AppComponent },
  {
    path: 'api-docs',
    redirectTo: () => {
      location.href = `${environment.apiBase}/docs`
      return location.pathname
    },
  },
]
