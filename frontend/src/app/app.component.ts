import { Component } from '@angular/core'
import { MapComponent } from "./map/map.component";
import { MareyComponent } from "./marey/marey.component";

@Component({
  selector: 'app-root',
  imports: [MapComponent, MareyComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent {}
