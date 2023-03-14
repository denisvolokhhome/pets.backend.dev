<?php

namespace App\Http\Controllers;

use App\Models\Pets;
use App\Models\Breeds;
use App\Models\Locations;
use Illuminate\Http\Request;
use DB;


class PetsController extends Controller
{
    public function index()
    {
        $pets = Pets::all();


        // Json Response
        return response()->json([
            'pets' => $pets
        ], 200);

    }

    public function store(Request $request)
    {

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



            // Create a pet
            Pets::create([
                'name' => $request->name,
                'breed_id' => $request->breed_id,
                'date_of_birth' => $request->date_of_birth,
                'gender' => $request->gender,
                'weight' => $request->weight,
                'location_id' => $request->location_id,
                'description' => $request->description,
                'image' => $request->image,
                'is_puppy' => $request->is_puppy,
                'litter_id' => $request->litter_id,
                'has_microchip' => $request->has_microchip,
                'has_vaccination' => $request->has_vaccination,
                'has_healthcertificate' => $request->has_healthcertificate,
                'has_dewormed' => $request->has_dewormed,
                'has_birthcertificate' => $request->has_birthcertificate
            ]);

            // Return Json Response
            return response()->json([
                'message' => "A new pet has been added"
            ], 200);
        } catch (\Exception $e) {
            // Return Json Response
            return response()->json([
                'message' => "Error adding pet" . $e
            ], 500);
        }
    }


    public function uploadImage(Request $request)
    {
        if(!$request->hasFile('image')) {
            return response()->json(['upload_file_not_found'], 400);
        }

        $allowedfileExtension=['pdf','jpg','png'];
        $file = $request->file('image');
        $errors = [];

        $extension = $file->getClientOriginalExtension();
        $check = in_array($extension,$allowedfileExtension);

        if($check) {


                $path = $request->image->store('public/images');
                $name = $request->image->getClientOriginalName();

                //store image file into directory and db
                $save = new Image();
                $save->title = $name;
                $save->path = $path;
                $save->save();


        } else {
            return response()->json(['invalid_file_format'], 422);
        }

        return response()->json(['file_uploaded'], 200);

    }


    public function destroy($id)
    {

        $pet = Pets::find($id);
        if (!$pet) {
            return response()->json([
                'message' => 'Entry not found.'
            ], 404);
        }
        $pet->delete();
        // Return Json Response
        return response()->json([
            'message' => 'Record ' . $id . ' deleted'
        ], 200);
    }

}
