import { Routes } from '@angular/router'
import { MapComponent } from './map/map.component'
import {environment} from '../environments/environment';

export const routes: Routes = [
  { path: '', redirectTo: 'map', pathMatch: 'full' },
  { path: 'map', component: MapComponent },
  {
    path: 'api-docs',
    redirectTo: () => {
      location.href = `${environment.apiBase}/docs`
      return location.pathname
    },
  },
]
