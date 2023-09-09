<?php

namespace App\Http\Controllers;

use App\Models\Pets;
use App\Models\Breeds;
use App\Models\Locations;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Storage;
use App\Services\FileService;
use Illuminate\Support\Facades\Log;
use DB;


class PetsController extends Controller
{

    private FileService $FileService;

    public function __construct(FileService $FileService)
    {
        $this->FileService = $FileService;
    }

    public function index()
    {
        $pets = Pets::all();


        // Json Response
        return response()->json([
            'pets' => $pets
        ], 200);

    }

    public function breeder($id)
    {
        $pets = Pets::where('pets.user_id', $id)
            ->join('locations', 'pets.location_id', '=', 'locations.id')
            ->join('breeds', 'pets.breed_id', '=', 'breeds.id')
            ->get(['pets.id AS pet_id', 'pets.created_at', 'pets.updated_at', 'pets.name AS name', 'breeds.name AS breed_name','pets.date_of_birth AS date_of_birth','pets.gender', 'pets.weight', 'locations.name AS location_name', 'locations.address1', 'locations.address2', 'locations.city', 'locations.country', 'locations.state', 'pets.description AS description', 'pets.image_path', 'pets.is_puppy']);

        // Json Response
        try {
            return response()->json($pets);

        } catch (\Exception $e) {
        // Return Json Response
            return response()->json([
                'message' => "Error getting pet " . $e,
            ], 500);
        }

    }

    public function show($id)
    {
        $pets = Pets::where('id', $id)->get();


        // Json Response
        return response()->json([
            'pets' => $pets
        ], 200);

    }

    public function store(Request $request)
    {

        try {

            $breed_id = DB::table('breeds')
                ->where('name' , '=', $request->breed_name)
                ->pluck('id');

            $location_id = DB::table('locations')
                ->where('name' , '=', $request->location_name)
                ->where('location_type' , '=', 'pet')
                ->pluck('id');

            $request['breed_id'] = $breed_id[0];
            $request['location_id'] = $location_id[0];



            $imageUpload = $this->FileService->uploadImage($request);
            if( $imageUpload->status() === 200){

                $request['image_path'] = $imageUpload->original['path'];
                $request['image_name'] = $imageUpload->original['fileName'];
                $request['error'] = $imageUpload->original['0'];

                Log::info('image path:'.$request['image_path']);
                Log::info('image name:'.$request['image_name']);
                Log::info('image error:'.$request['error']);


            }else{
                $request['error'] = $imageUpload->original['0'];
                Log::error('image not uploaded: '.$request['error']);

            }

            // Create a pet
            Pets::create([
                'name' => $request->name,
                'breed_id' => $request->breed_id,
                'date_of_birth' => $request->date_of_birth,
                'gender' => $request->gender,
                'weight' => $request->weight,
                'location_id' => $request->location_id,
                'description' => $request->description,
                'image_path' => $request->image_path,
                'image_name' => $request->image_name,
                'is_puppy' => $request->is_puppy,
                'litter_id' => $request->litter_id,
                'has_microchip' => $request->has_microchip,
                'has_vaccination' => $request->has_vaccination,
                'has_healthcertificate' => $request->has_healthcertificate,
                'has_dewormed' => $request->has_dewormed,
                'has_birthcertificate' => $request->has_birthcertificate,
                'user_id'=> $request->id,
                'error' => $request->error
            ]);

            // Return Json Response
            return response()->json($request);
        } catch (\Exception $e) {
            // Return Json Response
            return response()->json([
                'message' => "Error adding pet " . $e,
            ], 500);
        }
    }


    public function update(Request $request){
        try {

            $breed_id = DB::table('breeds')
                ->where('code' , '=', $request->breed_code)
                ->pluck('id');

            $location_id = DB::table('locations')
                ->where('name' , '=', $request->location_name)
                ->where('location_type' , '=', 'pet')
                ->pluck('id');

            $request['breed_id'] = $breed_id[0];
            $request['location_id'] = $location_id[0];


            $imageUpload = $this->uploadImage($request);
            Log::debug("test");
            if ($imageUpload){
                    if( $imageUpload->status() === 200){
                        $request['image_path'] = $imageUpload->original['path'];
                        $request['error'] = $imageUpload->original['0'];



                    }else{
                        $request['error'] = $imageUpload->original['0'];
                    }
            }else{
                $request['image_path'] = Pets::where('id', $request->id)->pluck('image')[0];
            }

            // update a pet
            Pets::where('id', $request->id)->update([
                'name' => $request->name,
                'breed_id' => $request->breed_id,
                'date_of_birth' => $request->date_of_birth,
                'gender' => $request->gender,
                'weight' => $request->weight,
                'location_id' => $request->location_id,
                'description' => $request->description,
                'image' => $request->image_path,
                'is_puppy' => $request->is_puppy,
                'litter_id' => $request->litter_id,
                'has_microchip' => $request->has_microchip,
                'has_vaccination' => $request->has_vaccination,
                'has_healthcertificate' => $request->has_healthcertificate,
                'has_dewormed' => $request->has_dewormed,
                'has_birthcertificate' => $request->has_birthcertificate,
                'error' => $request->error
            ]);

            // Return Json Response
            return response()->json([
                'message' => "Pet record was updated",
                'image upload status' => $request['error']
            ], 200);
        } catch (\Exception $e) {
            // Return Json Response
            return response()->json([
                'message' => "Error updating pet" . $e
            ], 500);
        }
    }

    public function markDeleted(Request $request)
    {
        $id = $request->id;
        $pet = Pets::find($id);
        if (!$pet) {
            return response()->json([
                'message' => 'Entry not found.'
            ], 404);
        }
        Pets::where('id',$id)->update(['is_deleted'=>1]);

        // Return Json Response
        return response()->json([
            'message' => 'Record ' . $id . ' marked as deleted'
        ], 200);
    }

}
