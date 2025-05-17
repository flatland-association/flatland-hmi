import { Component } from '@angular/core'
import { StateService } from '../state.service'
import { AsyncPipe, JsonPipe } from '@angular/common'

@Component({
  selector: 'app-map',
  imports: [AsyncPipe],
  templateUrl: './map.component.html',
  styleUrl: './map.component.scss',
})
export class MapComponent {
  constructor(public stateService: StateService) {}
}
